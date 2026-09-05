"""Executable patches for Madden NFL 09 (PS2): the playbook-editor caps, translated.

A gameplay change that no data file carries has to be a change to the boot ELF
``SLUS_217.70`` -- 32-bit MIPS words at EE addresses, delivered as a PCSX2
``.pnach`` first, exactly as the sibling PS2 module delivers its own.  This
lane is that pipeline, and it now carries one **real translation**:

* :data:`TRANSLATIONS` maps ``playbook_editor_caps`` to the five ``sltiu``
  immediates that bound the in-game create-a-playbook editor -- formations,
  sets, the set list, plays per book, and plays per set.  Each word's
  *original* is read from the user's own ELF before anything is written, at
  catalogue time, again at plan time, and a third time by ``verify``.
* Every other subject area the owner's Madden 09 static-analysis work has
  opened stays a **proposal** in :data:`PROPOSED_PATCHES`, and
  :meth:`Madden09CodePatchLane.translation` still refuses each one by name.
  A target there is a question, not a capability.

**Where the numbers come from.**  There is no host tool with a Madden 09 patch
list to read, the way the sibling module reads the Xbox studio's own panel, and
PCSX2's bundled ``patches.zip`` carries no file for either of this title's
CRCs -- measured, not assumed (``docs/product/MADDEN09_PS2_CODE_PATCHES.md``
records the measurement).  The five sites come from the owner's static research
[S] and every one was re-read and re-decoded against the boot executable before
being written here [M].

**What this lane does not claim.**  Nothing has been booted.  The caps this
patch raises are the *editor-side* layer only; the library layer beneath them
takes its capacity from each table's own on-disc header, and every shipped
table is packed exactly full.  :data:`SECOND_LAYER_NOTE` is the plain sentence
that says so, and it is repeated in the patch note, in the catalogue and in the
registry row.

**The only retail bytes here are the translation table itself** -- five
addresses and five words, which are the deliverable, exactly as they would be
in a pnach.  Everything else this file reports is measured from the user's own
image at run time: the ELF's program headers, its SHA-256 and its PCSX2 CRC.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.code_patches --selftest
    python3 -m mod_editor.games.madden09_ps2.code_patches --source DISC.iso
    python3 -m mod_editor.games.madden09_ps2.code_patches --source DISC.iso \\
        --recipe RECIPE.json --destination OUT.pnach

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from mod_editor.games._formats import ps2_elf
from mod_editor.games.contract import (
    Artifact,
    Catalogue,
    CodePatch,
    DeclaredRange,
    Edit,
    Field,
    GameIdentity,
    MipsPatch,
    MipsWord,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    require,
)

from . import containers

_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ps2_iso9660 as iso_lib  # noqa: E402

CAPABILITY_ID = "madden09ps2.gameplay.executable_patches"
#: Deliberately not ``gameplay.executable_patches``, which is what the sibling
#: PS2 module calls its own: the conformance harness gives each lane a working
#: directory named after its ``lane_id`` and shares one root across every
#: hosted game, so two games using the same short id collide on it.  Capability
#: ids are already game-scoped; this keeps the short id distinct too, and says
#: what the lane patches while it is at it.
LANE_ID = "gameplay.boot_elf_patches"
SURFACE = "gameplay_tuning_sliders"
RECIPE_SCHEMA = "madden09_ps2_code_patch_recipe/v1"
CATALOG_SCHEMA = "madden09_ps2_code_patch_catalog/v1"
WRITE_SCHEMA = "madden09_ps2_code_patch_write/v1"

#: The two ways a translated word reaches the game.  ``pnach`` is the default
#: and changes nothing on disc; ``disc`` writes the words into the boot ELF on
#: a NEW image through the shared fixed-allocation ISO9660 writer -- safe here
#: only because a word replacement never changes the executable's size.
DELIVERIES = ("pnach", "disc")

NOT_MAPPED = (
    "{patch_id} is not mapped to MIPS yet: no site in {boot} has been located for it, so "
    "there is nothing to translate. This lane translates {mapped} today; a recipe may carry "
    "hand-authored words while another translation is being proved. See "
    "docs/product/MADDEN09_PS2_CODE_PATCHES.md."
)


# --------------------------------------------------------------------------
# The translated patch: the create-a-playbook editor's five capacity checks
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CapSite:
    """One ``sltiu`` immediate that bounds a playbook-editor table.

    ``address`` is the EE virtual address of the instruction; ``original`` the
    word the retail and Deluxe executables both hold there [M]; ``shipped_cap``
    the number that immediate enforces (``IMM - 1``, because the code tests
    ``count + n < IMM``).  ``disassembly`` is what the word decodes to, written
    from the encoding, and ``parameter`` the recipe value that drives it.
    """

    table: str
    address: int
    original: int
    shipped_cap: int
    register: str
    disassembly: str
    parameter: str
    predicate: str
    meaning: str

    @property
    def immediate(self) -> int:
        return self.original & 0xFFFF

    def word_for(self, cap: int) -> int:
        """The same instruction with only its 16-bit immediate changed."""

        return (self.original & 0xFFFF0000) | ((cap + 1) & 0xFFFF)


#: The five capacity checks, each decoded against the boot ELF [M].  Their
#: addresses and words are the deliverable of this lane -- the same five pairs a
#: hand-written pnach for this title would carry -- and nothing else from any
#: executable is stored in this repository.
#:
#: Sourced from the owner's static-analysis repository [S]
#: (``docs/madden09-playbook-map.md`` section 1.6) and re-read, re-decoded and
#: re-confirmed against both the retail (PCSX2 CRC 38014255) and the Deluxe
#: (084562FF) executables before being written here [M].
CAP_SITES: tuple[CapSite, ...] = (
    CapSite(
        table="PBFM",
        address=0x007094A8,
        original=0x2C420015,
        shipped_cap=20,
        register="v0",
        disassembly="sltiu v0, v0, 21",
        parameter="formations_cap",
        predicate="room_for_formation @ 0x00709468",
        meaning="formations in one playbook",
    ),
    CapSite(
        table="PBST",
        address=0x007094D4,
        original=0x2C420015,
        shipped_cap=20,
        register="v0",
        disassembly="sltiu v0, v0, 21",
        parameter="sets_cap",
        predicate="room_for_formation @ 0x00709468",
        meaning="sets in one playbook",
    ),
    CapSite(
        table="SETL",
        address=0x00709500,
        original=0x2C520015,
        shipped_cap=20,
        register="s2",
        disassembly="sltiu s2, v0, 21",
        parameter="sets_cap",
        predicate="room_for_formation @ 0x00709468",
        meaning="set-list rows; the third table of the same conjunction as PBST, "
                "raised with it because the editor needs all three to have room",
    ),
    CapSite(
        table="PBPL",
        address=0x0070955C,
        original=0x2C510065,
        shipped_cap=100,
        register="s1",
        disassembly="sltiu s1, v0, 101",
        parameter="plays_cap",
        predicate="room_for_plays @ 0x00709520",
        meaning="plays in one playbook",
    ),
    CapSite(
        table="PBPL-per-SETL",
        address=0x006D2890,
        original=0x2C42003D,
        shipped_cap=60,
        register="v0",
        disassembly="sltiu v0, v0, 61",
        parameter="plays_per_set_cap",
        predicate="play-commit handler @ 0x006D2848",
        meaning="plays in one set -- a check Madden 2004 did not have at all",
    ),
)

PLAYBOOK_CAPS_PATCH_ID = "playbook_editor_caps"
PLAYBOOK_CAPS_TITLE = "Playbook editor capacity checks"

#: The recipe parameters, in the order the editor draws them, each with the
#: shipped cap it defaults to and the sites it drives.
CAP_PARAMETERS: tuple[str, ...] = ("formations_cap", "sets_cap", "plays_cap", "plays_per_set_cap")

#: The largest cap a 16-bit ``sltiu`` immediate can carry.  ``IMM = cap + 1``
#: and the immediate field is 16 bits, so the biggest immediate is 0xFFFF and
#: the biggest cap one below it.
MAX_IMMEDIATE = 0xFFFF
MAX_CAP = MAX_IMMEDIATE - 1

#: ``sltiu`` **sign-extends** its 16-bit immediate before the unsigned compare,
#: so an immediate of 0x8000 or more compares as a 64-bit value with every high
#: bit set and the test becomes always-true.  A cap at or below this number is
#: still literally the number the code enforces; above it the site stops being a
#: cap and becomes an unconditional pass.  Both are allowed -- the second is how
#: a user removes the check entirely -- but the difference is stated, never
#: hidden, and the patch note repeats it for any cap that crosses the line.
SIGN_EXTENSION_CAP = 0x7FFF - 1

SECOND_LAYER_NOTE = (
    "Editor-side layer only, and nothing here has been booted. These five words move the "
    "create-a-playbook editor's own sltiu checks and nothing else. Beneath them the database "
    "library keeps its own per-table capacity, which the header loader at 0x0081A1F8 fills "
    "from each table's on-disc max_records, and every one of the 1,944 tables the disc ships "
    "has record_count == max_records -- packed exactly full, no slack. The insert-time guard "
    "compares record_count against that capacity and, when they are equal, returns status 19 "
    "instead of adding a row. So raising these caps is expected to let the editor ask for a "
    "21st set and then be refused one row lower down, until a second layer exists. That second "
    "layer is not shipped here and the measured reason is in "
    "docs/product/MADDEN09_PS2_CODE_PATCHES.md: table_set_capacity at 0x0082A6A0 is a "
    "subroutine, not an immediate -- five of its six callers hand it the capacity they just read "
    "out of the table object -- so raising it needs new code at a hook site the owner's research "
    "records as located but not pinned, and new code cannot be verified without a boot."
)

#: The subject areas a Madden 09 executable patch would reach, as the owner's
#: own static-analysis repository has opened them [S]: each name below is one
#: of that work's requirement documents, restated here as a question this lane
#: cannot yet answer.  **No address, offset or code byte is carried** -- only
#: the name of the behaviour and the fact that nothing is located.
PROPOSED_PATCHES: tuple[tuple[str, str, str], ...] = (
    ("ai_play_calling",
     "AI play calling",
     "Which play the CPU coach selects, and the weights behind it."),
    ("block_dominance",
     "Blocking dominance",
     "How a one-on-one block resolves between a blocker and a rusher."),
    ("blocking_intent",
     "Blocking assignment intent",
     "Which defender each blocker picks up before the snap resolves."),
    ("catch_and_fumble",
     "Catch and fumble outcomes",
     "The reception and ball-security rolls at the catch point."),
    ("defense_fatigue",
     "Defensive fatigue",
     "How fast defenders tire, and what tiring costs them."),
    ("double_team",
     "Double teams",
     "When two blockers commit to one rusher and when one peels off."),
)


def _cap_defaults() -> Dict[str, int]:
    values: Dict[str, int] = {}
    for site in CAP_SITES:
        values.setdefault(site.parameter, site.shipped_cap)
    return values


def _floor(parameter: str) -> int:
    """The lowest cap a parameter may take: the shipped cap it defaults to."""

    return max(site.shipped_cap for site in CAP_SITES if site.parameter == parameter)


def check_cap_parameters(parameters: Mapping[str, Any]) -> Dict[str, int]:
    """Validate a recipe's caps and fill in the shipped defaults, or refuse."""

    require(isinstance(parameters, Mapping),
            f"{PLAYBOOK_CAPS_PATCH_ID}: parameters must be a mapping of "
            f"{', '.join(CAP_PARAMETERS)} to whole numbers.")
    unknown = sorted(set(parameters) - set(CAP_PARAMETERS))
    require(not unknown,
            f"{PLAYBOOK_CAPS_PATCH_ID}: {', '.join(unknown)} is not one of this patch's "
            f"parameters; give {', '.join(CAP_PARAMETERS)}.")
    values = _cap_defaults()
    for name in CAP_PARAMETERS:
        if name not in parameters:
            continue
        value = parameters[name]
        require(not isinstance(value, bool) and isinstance(value, int),
                f"{PLAYBOOK_CAPS_PATCH_ID}: {name} is {value!r}; give a whole number of rows "
                f"between {_floor(name)} and {MAX_CAP}.")
        floor = _floor(name)
        require(value >= floor,
                f"{PLAYBOOK_CAPS_PATCH_ID}: {name}={value} is below the {floor} this "
                f"executable already enforces. This patch raises the editor's ceiling; it "
                f"does not lower it, because books the disc already ships hold more than the "
                f"editor's cap and shrinking the check would strand them.")
        require(value <= MAX_CAP,
                f"{PLAYBOOK_CAPS_PATCH_ID}: {name}={value} needs an immediate of {value + 1}, "
                f"which does not fit the 16 bits an sltiu carries; the largest cap is {MAX_CAP}.")
        values[name] = value
    return values


def _translate_playbook_caps(parameters: Mapping[str, Any]) -> tuple[MipsWord, ...]:
    """The words for the caps a recipe actually raises; unchanged caps write nothing."""

    values = check_cap_parameters(parameters)
    words: List[MipsWord] = []
    for site in CAP_SITES:
        cap = values[site.parameter]
        if cap == site.shipped_cap:
            continue
        words.append(MipsWord(site.address, site.original, site.word_for(cap)))
    require(words,
            f"{PLAYBOOK_CAPS_PATCH_ID}: every cap is already what this executable enforces "
            f"({', '.join(f'{name}={value}' for name, value in sorted(_cap_defaults().items()))}), "
            f"so there is no word to write. Raise at least one of "
            f"{', '.join(CAP_PARAMETERS)}.")
    return tuple(words)


def playbook_caps_note(parameters: Mapping[str, Any]) -> str:
    """The sentence that ships in the pnach beside the words."""

    values = check_cap_parameters(parameters)
    raised = [f"{site.table} {site.shipped_cap}->{values[site.parameter]}"
              for site in CAP_SITES if values[site.parameter] != site.shipped_cap]
    note = "Playbook editor caps: " + ", ".join(raised) + ". " + SECOND_LAYER_NOTE
    degenerate = sorted({site.parameter for site in CAP_SITES
                         if values[site.parameter] > SIGN_EXTENSION_CAP})
    if degenerate:
        note += (f" Note: {', '.join(degenerate)} is above {SIGN_EXTENSION_CAP}, so its "
                 f"immediate sign-extends and the check becomes an unconditional pass rather "
                 f"than a larger number.")
    return note


#: patch_id -> translator(parameters) -> words.  One entry today.
TRANSLATIONS: Dict[str, Callable[[Mapping[str, Any]], tuple[MipsWord, ...]]] = {
    PLAYBOOK_CAPS_PATCH_ID: _translate_playbook_caps,
}

#: Notes for the translated patches, keyed the same way.
TRANSLATION_NOTES: Dict[str, Callable[[Mapping[str, Any]], str]] = {
    PLAYBOOK_CAPS_PATCH_ID: playbook_caps_note,
}


# --------------------------------------------------------------------------
# The synthetic executable CI proves the lane on
# --------------------------------------------------------------------------

#: The synthetic ELF's base address: below the lowest translated site, so the
#: conformance harness can drive the **real** translation and not only a
#: hand-authored word.  The seven words at the base are a do-nothing R5900 leaf
#: function, written from the instruction encoding and lifted from no image.
SYNTHETIC_BASE = 0x006D2000
SYNTHETIC_WORDS = (0x27BDFFF0, 0xAFBF0000, 0x24020001, 0x8FBF0000,
                   0x27BD0010, 0x03E00008, 0x00000000)


def synthetic_elf_words() -> tuple[int, ...]:
    """The synthetic image's code: the leaf function, then the five cap sites.

    Every other word is zero (``nop``).  The five originals are copied from
    :data:`CAP_SITES`, which is this file's own translation table, so the
    synthetic source needs nothing read out of a retail executable.
    """

    highest = max(site.address for site in CAP_SITES)
    count = (highest + 4 - SYNTHETIC_BASE) // 4
    words = [0] * count
    for index, word in enumerate(SYNTHETIC_WORDS):
        words[index] = word
    for site in CAP_SITES:
        words[(site.address - SYNTHETIC_BASE) // 4] = site.original
    return tuple(words)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: int) -> str:
    return f"{value & 0xFFFFFFFF:08X}"


def _word_value(value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise Refusal(f"{what} must be a 32-bit word, not a boolean.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if not value.lower().startswith("0x") else int(value, 0)
        except ValueError as exc:
            raise Refusal(
                f"{what} is {value!r}, which is not a 32-bit hexadecimal word; write it "
                f"as eight hex digits."
            ) from exc
    raise Refusal(f"{what} is {value!r}; give a 32-bit word as an int or eight hex digits.")


def _words_from(values: Sequence[Any], patch_id: str) -> tuple[MipsWord, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        raise Refusal(f"{patch_id}: 'mips' must be a non-empty list of word rows.")
    words: List[MipsWord] = []
    for number, row in enumerate(values):
        if not isinstance(row, Mapping):
            raise Refusal(f"{patch_id}: word {number} must be a mapping with address, original and replacement.")
        unknown = sorted(set(row) - {"address", "original", "replacement"})
        if unknown:
            raise Refusal(f"{patch_id}: word {number} carries {', '.join(unknown)}; give address, original and replacement only.")
        words.append(MipsWord(
            address=_word_value(row.get("address"), f"{patch_id} word {number} address"),
            original=_word_value(row.get("original"), f"{patch_id} word {number} original"),
            replacement=_word_value(row.get("replacement"), f"{patch_id} word {number} replacement"),
        ))
    return tuple(words)


def translated_patches() -> tuple[CodePatch, ...]:
    """The patches this lane can translate today."""

    return (
        CodePatch(
            patch_id=PLAYBOOK_CAPS_PATCH_ID,
            title=PLAYBOOK_CAPS_TITLE,
            surface=SURFACE,
            parameters={
                name: {"type": "int", "min": _floor(name), "max": MAX_CAP,
                       "default": _floor(name)}
                for name in CAP_PARAMETERS
            },
            host_site={
                "executable": containers.BOOT_FILE,
                "serial": containers.SERIAL,
                "kind": "code",
                "flag": PLAYBOOK_CAPS_PATCH_ID,
                "catalogue": "the owner's Madden 09 static-analysis research, re-read and "
                             "re-decoded against the boot ELF by this lane",
                "applier": None,
                "sites": [
                    {"table": site.table, "address": _hex(site.address),
                     "original": _hex(site.original), "shipped_cap": site.shipped_cap,
                     "disassembly": site.disassembly, "predicate": site.predicate,
                     "parameter": site.parameter}
                    for site in CAP_SITES
                ],
            },
            note=("The five sltiu immediates the create-a-playbook editor tests before it "
                  "adds a formation, a set, a set-list row, a play, or a play inside one "
                  "set. Each is count + n < IMM, so the cap is IMM - 1 and only the "
                  "immediate changes. " + SECOND_LAYER_NOTE),
        ),
    )


def proposed_patches() -> tuple[CodePatch, ...]:
    """The rest of the catalogue: named questions, every one unmapped."""

    return tuple(
        CodePatch(
            patch_id=patch_id,
            title=title,
            surface=SURFACE,
            parameters={"enabled": {"type": "bool", "default": False}},
            host_site={
                "executable": containers.BOOT_FILE,
                "serial": containers.SERIAL,
                "kind": "code",
                "flag": patch_id,
                "catalogue": "proposal; no host tool carries a Madden 09 patch list",
                "applier": None,
            },
            note=f"{note} No word has been located for it.",
        )
        for patch_id, title, note in PROPOSED_PATCHES
    )


class Madden09CodePatchLane:
    """The executable-patch lane for SLUS-21770: the playbook caps, translated."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = SURFACE
    page = "gameplay"
    title = "Executable patches (playbook editor caps; pnach or on-disc)"
    classification = "offline-writer-proved"
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_code_patches.sh",
        "tools/validate_madden09_ps2_code_patches.bat",
    )
    #: The lane's DEFAULT destination is a pnach, a new small text file beside
    #: the image, so the destination does not keep the source's byte length.
    #: The optional on-disc route does keep it exactly, and enforces that
    #: itself: ``_compare_images`` refuses a destination of a different size
    #: and refuses any differing byte outside a declared four-byte range.
    fixed_allocation = False

    def __init__(self, identity: GameIdentity) -> None:
        self.identity = identity

    # -- the code-patch protocol ---------------------------------------

    def patches(self) -> tuple[CodePatch, ...]:
        return translated_patches() + proposed_patches()

    def translation(self, patch_id: str, parameters: Mapping[str, Any]) -> MipsPatch:
        known = {patch.patch_id for patch in self.patches()}
        require(patch_id in known,
                f"{patch_id!r} is not one of this lane's {len(known)} patches; "
                f"choose one of {', '.join(sorted(known))}.")
        translator = TRANSLATIONS.get(patch_id)
        if translator is None:
            raise Refusal(NOT_MAPPED.format(patch_id=patch_id, boot=containers.BOOT_FILE,
                                            mapped=", ".join(sorted(TRANSLATIONS))))
        words = translator(parameters)  # refuses before any note is written
        note_of = TRANSLATION_NOTES.get(patch_id)
        note = note_of(parameters) if note_of is not None else "translated"
        return MipsPatch(patch_id, words, self._retail_identity(), parameters, note)

    def emit_pnach(self, patches: Sequence[MipsPatch], crc: str) -> str:
        require(bool(patches), "A pnach needs at least one patch.")
        comments = [f"{patch.patch_id}: {patch.note or 'translated'}" for patch in patches]
        comments.append(
            "Emitted by the PS2 Madden 09 module's executable-patch lane; every word was "
            "checked against the boot ELF it names."
        )
        words = [ps2_elf.PnachPatch(word.address, word.replacement)
                 for patch in patches for word in patch.words]
        return ps2_elf.emit_pnach(f"Madden NFL 09 ({containers.SERIAL})", crc, words, comments)

    def verify_pnach(self, pnach_text: str, source: Path,
                     expected: Sequence[MipsPatch]) -> Verdict:
        try:
            document = ps2_elf.parse_pnach(pnach_text)
        except ps2_elf.PnachError as exc:
            return Verdict(False, f"Verification failed: {exc}")
        try:
            elf, _boot = ps2_elf.read_boot_elf(Path(source))
            segments = ps2_elf.parse_program_headers(elf, containers.BOOT_FILE)
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}")
        crc = ps2_elf.pcsx2_crc(elf)
        if document.crc != crc:
            return Verdict(False, f"Verification failed: the pnach names CRC {document.crc} "
                                  f"but this boot ELF's CRC is {crc}.")
        wanted = {word.address: word for patch in expected for word in patch.words}
        found = {patch.address: patch for patch in document.patches}
        missing = sorted(set(wanted) - set(found))
        extra = sorted(set(found) - set(wanted))
        if missing or extra:
            return Verdict(False, "Verification failed: the pnach declares "
                           + (f"undeclared addresses {[_hex(a) for a in extra]}" if extra else "")
                           + (" and " if extra and missing else "")
                           + (f"misses {[_hex(a) for a in missing]}" if missing else "") + ".")
        for address, word in wanted.items():
            if found[address].value != word.replacement:
                return Verdict(False, f"Verification failed: {_hex(address)} writes "
                                      f"{_hex(found[address].value)}, not {_hex(word.replacement)}.")
            if not found[address].enabled:
                return Verdict(False, f"Verification failed: the line for {_hex(address)} is disabled.")
            try:
                original = ps2_elf.read_word(elf, segments, address)
            except ps2_elf.PnachError as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if original != word.original:
                return Verdict(False, f"Verification failed: the ELF holds {_hex(original)} at "
                                      f"{_hex(address)}, not the {_hex(word.original)} the recipe expects.")
        return Verdict(True,
                       f"{len(wanted)} word(s) verified against the boot ELF (CRC {crc}); "
                       f"nothing else declared.",
                       {"result": "PASS", "crc": crc, "words": len(wanted)})

    # -- the lane protocol ---------------------------------------------

    def _retail_identity(self) -> Dict[str, Any]:
        return {
            "serial": containers.SERIAL,
            "boot_file": containers.BOOT_FILE,
            "sha256": self.identity.executable_sha256[0] if self.identity.executable_sha256 else None,
            "pcsx2_crc": containers.RETAIL_ELF_CRC,
        }

    def _elf(self, source: Path):
        elf, boot = ps2_elf.read_boot_elf(Path(source))
        segments = ps2_elf.parse_program_headers(elf, boot.get("boot_file") or containers.BOOT_FILE)
        digest = _sha256(elf)
        editions = {
            containers.RETAIL_BOOT_ELF_SHA256: containers.RETAIL_EDITION,
            containers.DELUXE_BOOT_ELF_SHA256: containers.DELUXE_EDITION,
        }
        identity = {
            "serial": boot.get("serial"),
            "boot_file": boot.get("boot_file"),
            "sha256": digest,
            "pcsx2_crc": ps2_elf.pcsx2_crc(elf),
            "edition": editions.get(digest, "unknown"),
            "retail": digest in self.identity.executable_sha256,
            "segments": [
                {"index": s.index, "offset": s.offset, "vaddr": s.vaddr,
                 "filesz": s.filesz, "memsz": s.memsz, "executable": s.executable}
                for s in segments
            ],
        }
        return elf, segments, identity

    @staticmethod
    def _site_rows(elf: bytes, segments) -> List[Dict[str, Any]]:
        """Every cap site as the user's own ELF holds it right now [M]."""

        rows: List[Dict[str, Any]] = []
        for site in CAP_SITES:
            row: Dict[str, Any] = {
                "table": site.table,
                "address": _hex(site.address),
                "expected": _hex(site.original),
                "shipped_cap": site.shipped_cap,
                "disassembly": site.disassembly,
                "predicate": site.predicate,
                "parameter": site.parameter,
                "meaning": site.meaning,
            }
            try:
                found = ps2_elf.read_word(elf, segments, site.address)
            except ps2_elf.PnachError as exc:
                row.update({"found": None, "matches": False, "reason": str(exc)})
            else:
                row.update({"found": _hex(found), "matches": found == site.original,
                            "found_cap": (found & 0xFFFF) - 1})
            rows.append(row)
        return rows

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        if progress is not None:
            progress("Reading the boot ELF…")
        elf, segments, identity = self._elf(Path(source))
        if progress is not None:
            progress("Reading each capacity check out of this executable…")
        sites = self._site_rows(elf, segments)
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        for patch in self.patches():
            mapped = patch.patch_id in TRANSLATIONS
            row: Dict[str, Any] = {
                "patch_id": patch.patch_id,
                "title": patch.title,
                "surface": patch.surface,
                "mapped": mapped,
                "note": patch.note,
            }
            if mapped and patch.patch_id == PLAYBOOK_CAPS_PATCH_ID:
                row["sites"] = sites
                row["sites_match"] = all(site["matches"] for site in sites)
            rows.append(row)
            targets.append(Target(
                key=patch.patch_id,
                label=f"{patch.title} — {'translated' if mapped else 'no site located yet'}",
                detail=patch.note,
                budget=(f"{len(CAP_SITES)} 32-bit words at EE addresses inside the boot ELF; "
                        f"only each sltiu's 16-bit immediate changes"
                        if mapped else
                        "32-bit words at EE addresses inside the boot ELF; delivered as a pnach"),
                searchable=f"{patch.patch_id} {patch.title}",
                raw=row,
                fields=self._fields_for(patch.patch_id, mapped),
            ))
        document = {
            "schema": CATALOG_SCHEMA,
            "elf": identity,
            "patches": rows,
            "translations_available": sum(1 for row in rows if row["mapped"]),
            "deliveries": list(DELIVERIES),
            "second_layer": SECOND_LAYER_NOTE,
        }
        return Catalogue(CATALOG_SCHEMA, self.lane_id, str(source), tuple(targets), document)

    @staticmethod
    def _fields_for(patch_id: str, mapped: bool) -> tuple[Field, ...]:
        if patch_id == PLAYBOOK_CAPS_PATCH_ID:
            labels = {
                "formations_cap": ("Formations per playbook", "PBFM"),
                "sets_cap": ("Sets per playbook", "PBST and SETL"),
                "plays_cap": ("Plays per playbook", "PBPL"),
                "plays_per_set_cap": ("Plays per set", "the per-set PBPL check"),
            }
            fields = []
            for name in CAP_PARAMETERS:
                label, tables = labels[name]
                floor = _floor(name)
                fields.append(Field(
                    name, "int", label,
                    f"The editor's cap on {tables}. This executable enforces {floor}; leave it "
                    f"there to write no word for it. Above {SIGN_EXTENSION_CAP} the immediate "
                    f"sign-extends and the check becomes an unconditional pass.",
                    minimum=floor, maximum=MAX_CAP,
                ))
            fields.append(Field(
                "second_layer", "note", "What this does not do", SECOND_LAYER_NOTE,
                read_only=True,
            ))
            return tuple(fields)
        # A proposal has no located site, so the studio draws its control
        # disabled rather than offering a switch that can only ever refuse.
        # The command line still takes hand-authored words for it, which is how
        # a maintainer proves the next translation.
        return (
            Field("enabled", "bool", "Enabled",
                  "Cannot be turned on: no site in the boot ELF has been located for this "
                  "subject area, so there is nothing to write.",
                  read_only=True),
            Field("mips", "note", "Hand-authored words",
                  "A maintainer proving a translation may hand this lane its own "
                  "address/original/replacement rows through the recipe.",
                  read_only=True),
        )

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"enabled", "parameters", "mips", "deliver"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane takes; "
                    f"give parameters, a delivery, or hand-authored mips words.")
        delivery = values.get("deliver")
        if delivery is not None and delivery not in DELIVERIES:
            return (f"{target.key}: deliver={delivery!r} is not a route this lane has; "
                    f"give one of {', '.join(DELIVERIES)}.")
        if values.get("mips") is not None:
            try:
                _words_from(values["mips"], target.key)
            except Refusal as exc:
                return str(exc)
            return None
        parameters = values.get("parameters", {})
        if not isinstance(parameters, Mapping):
            return f"{target.key}: parameters must be a mapping of parameter names to values."
        if not target.raw.get("mapped"):
            return NOT_MAPPED.format(patch_id=target.key, boot=containers.BOOT_FILE,
                                     mapped=", ".join(sorted(TRANSLATIONS)))
        if target.raw.get("sites") is not None and not target.raw.get("sites_match"):
            wrong = [site["table"] for site in target.raw["sites"] if not site["matches"]]
            return (f"{target.key}: this executable does not hold the word this lane expects at "
                    f"{', '.join(wrong)}, so its caps were not derived against the image you "
                    f"opened. Open the retail or Deluxe SLUS-21770 disc.")
        try:
            check_cap_parameters(parameters)
            TRANSLATIONS[target.key](parameters)
        except Refusal as exc:
            return str(exc)
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        delivery = None
        for edit in edits:
            row: Dict[str, Any] = {
                "patch": edit.target_key,
                "parameters": dict(edit.values.get("parameters", {}) or {}),
            }
            if edit.values.get("deliver") is not None:
                asked = str(edit.values["deliver"])
                require(delivery is None or delivery == asked,
                        f"one recipe is delivered one way, and these edits ask for both "
                        f"{delivery} and {asked}; stage them separately.")
                delivery = asked
            if edit.values.get("mips") is not None:
                row["mips"] = [
                    {"address": _hex(_word_value(item["address"], "address")),
                     "original": _hex(_word_value(item["original"], "original")),
                     "replacement": _hex(_word_value(item["replacement"], "replacement"))}
                    for item in edit.values["mips"]
                ]
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        recipe: Dict[str, Any] = {"schema": RECIPE_SCHEMA, "patches": rows}
        if delivery is not None:
            recipe["deliver"] = delivery
        return recipe

    def _delivery(self, recipe: Mapping[str, Any]) -> str:
        delivery = recipe.get("deliver", "pnach")
        require(delivery in DELIVERIES,
                f"deliver={delivery!r} is not a route this lane has; "
                f"give one of {', '.join(DELIVERIES)}.")
        return str(delivery)

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == RECIPE_SCHEMA,
                f"recipe schema is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {RECIPE_SCHEMA}")
        require(set(recipe) <= {"schema", "patches", "deliver"},
                "a recipe carries schema, patches and an optional deliver, and nothing else")
        rows = recipe.get("patches")
        require(isinstance(rows, list) and rows, "a recipe must carry a non-empty 'patches' list")
        seen: set = set()
        entries = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("patch"), str) and row["patch"],
                    f"patch {number} must name the patch it translates")
            require(set(row) <= {"patch", "parameters", "mips", "note"},
                    f"patch {number} carries unknown keys")
            require(row["patch"] not in seen,
                    f"{row['patch']} appears twice; one patch is delivered once")
            seen.add(row["patch"])
            entries.append(dict(row))
        return entries

    def _mips(self, entry: Mapping[str, Any], identity: Mapping[str, Any]) -> MipsPatch:
        parameters = entry.get("parameters") or {}
        require(isinstance(parameters, Mapping), f"{entry['patch']}: parameters must be a mapping")
        if entry.get("mips") is not None:
            return MipsPatch(entry["patch"], _words_from(entry["mips"], entry["patch"]),
                             identity, parameters, str(entry.get("note") or "hand-authored"))
        translated = self.translation(entry["patch"], parameters)
        if entry.get("note"):
            return MipsPatch(translated.patch_id, translated.words, identity,
                             translated.parameters, str(entry["note"]))
        return MipsPatch(translated.patch_id, translated.words, identity,
                         translated.parameters, translated.note)

    # -- planning -------------------------------------------------------

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        entries = self._entries(recipe)
        delivery = self._delivery(recipe)
        elf, segments, identity = self._elf(Path(source))
        catalogued = catalogue.document.get("elf", {})
        require(identity["sha256"] == catalogued.get("sha256"),
                "the boot ELF changed since it was catalogued; rebuild the catalogue from this image")
        patches = []
        seen_addresses: set = set()
        offsets: Dict[int, int] = {}
        for entry in entries:
            catalogue.target(entry["patch"])  # the catalogue's own sentence for an unknown patch
            patch = self._mips(entry, identity)
            for word in patch.words:
                require(word.address not in seen_addresses,
                        f"{patch.patch_id}: {_hex(word.address)} is written twice in this recipe")
                seen_addresses.add(word.address)
                try:
                    actual = ps2_elf.read_word(elf, segments, word.address)
                    offsets[word.address] = ps2_elf.file_offset(segments, word.address)
                except ps2_elf.PnachError as exc:
                    raise Refusal(f"{patch.patch_id}: {exc}") from exc
                require(actual == word.original,
                        f"{patch.patch_id}: the ELF holds {_hex(actual)} at {_hex(word.address)}, "
                        f"not the {_hex(word.original)} the recipe expects; these words were not "
                        f"derived against this executable")
            patches.append(patch)
        document: Dict[str, Any] = {
            "crc": identity["pcsx2_crc"],
            "elf_sha256": identity["sha256"],
            "delivery": delivery,
            "patches": [self._patch_row(patch, offsets) for patch in patches],
        }
        ranges: tuple[DeclaredRange, ...] = ()
        if delivery == "disc":
            extent = self._boot_extent(Path(source))
            document["boot_extent"] = extent
            ranges = tuple(
                DeclaredRange(extent["byte_offset"] + offsets[word.address], 4,
                              f"{patch.patch_id}:{_hex(word.address)}")
                for patch in patches for word in patch.words
            )
            document["image_offsets"] = {
                _hex(word.address): extent["byte_offset"] + offsets[word.address]
                for patch in patches for word in patch.words
            }
        return Plan(self.lane_id, tuple(entry["patch"] for entry in entries), ranges, document)

    @staticmethod
    def _boot_extent(source: Path) -> Dict[str, Any]:
        """Where the boot ELF's bytes sit inside the user's image [M]."""

        try:
            image = iso_lib.open_image(str(source))
            identity = iso_lib.boot_identity(image)
            boot2 = identity.get("boot2")
            entry = iso_lib.find(image, boot2) if boot2 else None
        except (iso_lib.Iso9660Error, OSError, ValueError) as exc:
            raise Refusal(f"{source}: {exc}") from exc
        require(entry is not None and not entry.is_dir,
                f"{source}: SYSTEM.CNF names no readable boot ELF, so there is nothing to patch on disc.")
        return {
            "path": entry.path,
            "raw_name": entry.raw_name,
            "lba": entry.lba,
            "length": entry.length,
            "byte_offset": entry.lba * image.sector_size + image.data_offset,
            "sector_size": image.sector_size,
            "data_offset": image.data_offset,
        }

    @staticmethod
    def _patch_row(patch: MipsPatch, offsets: Optional[Mapping[int, int]] = None) -> Dict[str, Any]:
        offsets = offsets or {}
        return {"patch_id": patch.patch_id, "note": patch.note,
                "parameters": dict(patch.parameters),
                "words": [{"address": _hex(w.address), "original": _hex(w.original),
                           "replacement": _hex(w.replacement),
                           "elf_offset": offsets.get(w.address)} for w in patch.words]}

    @staticmethod
    def _patches_from_rows(rows: Sequence[Mapping[str, Any]],
                           identity: Mapping[str, Any]) -> List[MipsPatch]:
        out = []
        for row in rows:
            words = _words_from([{k: v for k, v in word.items() if k != "elf_offset"}
                                 for word in row["words"]], row["patch_id"])
            out.append(MipsPatch(row["patch_id"], words, identity,
                                 row.get("parameters", {}), str(row.get("note", ""))))
        return out

    # -- building -------------------------------------------------------

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(),
                f"{destination} is the source image; a build writes a NEW file beside it.")
        require(not destination.exists(),
                f"destination {destination} already exists; refusing to overwrite")
        planned = self.plan(source, recipe, catalogue)
        identity = dict(catalogue.document["elf"])
        patches = self._patches_from_rows(planned.document["patches"], identity)
        if planned.document["delivery"] == "disc":
            return self._build_disc(source, destination, planned, patches, identity)
        return self._build_pnach(source, destination, planned, patches, identity)

    def _build_pnach(self, source: Path, destination: Path, planned: Plan,
                     patches: Sequence[MipsPatch], identity: Mapping[str, Any]) -> Receipt:
        payload = self.emit_pnach(patches, planned.document["crc"]).encode("utf-8")
        try:
            with open(destination, "xb") as handle:  # exclusive: never overwrites
                handle.write(payload)
        except FileExistsError as exc:
            raise Refusal(f"destination {destination} appeared meanwhile; refusing to overwrite") from exc
        digest = _sha256(payload)
        document = {
            "schema": WRITE_SCHEMA,
            "source": str(source),
            "destination": str(destination),
            "crc": planned.document["crc"],
            "elf": {k: v for k, v in identity.items() if k != "segments"},
            "patches": list(planned.document["patches"]),
            "pnach_sha256": digest,
            "delivery": "pnach",
            "note": "Drop the file in PCSX2's patches folder as <CRC>.pnach; nothing on the disc changed.",
            "second_layer": SECOND_LAYER_NOTE,
        }
        return Receipt(WRITE_SCHEMA, self.lane_id, str(source), str(destination), (), document,
                       artifacts=(Artifact(str(destination), digest, "pnach"),))

    def _build_disc(self, source: Path, destination: Path, planned: Plan,
                    patches: Sequence[MipsPatch], identity: Mapping[str, Any]) -> Receipt:
        """Write the words into the boot ELF on a NEW image, same size, in place.

        An ELF word patch never changes the executable's length, which is the
        one thing the shared fixed-allocation ISO writer needs: the replacement
        fits the extent the file already owns exactly, nothing moves, and the
        directory record's declared length is rewritten with the value it
        already had.
        """

        import ps2_iso9660_writer as iso_writer  # local: the pnach route needs no writer

        elf, segments, _identity = self._elf(source)
        patched = bytearray(elf)
        for patch in patches:
            for word in patch.words:
                offset = ps2_elf.file_offset(segments, word.address)
                struct.pack_into("<I", patched, offset, word.replacement)
        require(len(patched) == len(elf),
                "a word patch must not change the executable's length; refusing to write")
        extent = planned.document["boot_extent"]
        try:
            report = iso_writer.replace_files(source, destination, {extent["path"]: bytes(patched)})
        except (iso_writer.IsoWriteError, OSError, ValueError) as exc:
            raise Refusal(f"the on-disc route refused this image: {exc}") from exc
        digest = _sha256(bytes(patched))
        document = {
            "schema": WRITE_SCHEMA,
            "source": str(source),
            "destination": str(destination),
            "crc": planned.document["crc"],
            "elf": {k: v for k, v in identity.items() if k != "segments"},
            "patches": list(planned.document["patches"]),
            "delivery": "disc",
            "patched_elf_sha256": digest,
            "boot_extent": extent,
            "image_offsets": planned.document["image_offsets"],
            "iso_write_report": iso_writer.report_to_json(report),
            "note": ("The words are in the boot ELF on the new image; the source image was not "
                     "touched and no pnach is needed."),
            "second_layer": SECOND_LAYER_NOTE,
        }
        return Receipt(WRITE_SCHEMA, self.lane_id, str(source), str(destination),
                       planned.declared_ranges, document)

    # -- verifying ------------------------------------------------------

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        destination = Path(destination)
        try:
            expected = self._patches_from_rows(receipt.document.get("patches", []),
                                               dict(receipt.document.get("elf", {})))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: the receipt is malformed: {exc}")
        if not expected:
            return Verdict(False, "Verification failed: the receipt declares no patches.")
        if receipt.document.get("delivery") == "disc":
            return self._verify_disc(Path(source), destination, receipt, expected)
        try:
            payload = destination.read_bytes()
        except OSError as exc:
            return Verdict(False, f"Verification failed: {exc}")
        for artifact in receipt.artifacts:
            if Path(artifact.path) == destination and _sha256(payload) != artifact.sha256:
                return Verdict(False, "Verification failed: the pnach on disk is not the file "
                                      "the receipt recorded.")
        return self.verify_pnach(payload.decode("utf-8", "replace"), Path(source), expected)

    def _verify_disc(self, source: Path, destination: Path, receipt: Receipt,
                     expected: Sequence[MipsPatch]) -> Verdict:
        """Re-derive the whole claim from the two images, importing none of the writer.

        Reads the destination's boot ELF through the ISO reader independently of
        anything the build recorded, checks every declared word holds its
        replacement, and checks that **every other byte** of the executable --
        and then of the whole image -- is what the source held.
        """

        try:
            after, boot_after = ps2_elf.read_boot_elf(destination)
            before, boot_before = ps2_elf.read_boot_elf(source)
            segments = ps2_elf.parse_program_headers(after, containers.BOOT_FILE)
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}")
        if boot_after.get("boot_file") != boot_before.get("boot_file"):
            return Verdict(False, "Verification failed: the new image boots a different executable.")
        if len(after) != len(before):
            return Verdict(False, f"Verification failed: the new boot ELF is {len(after)} bytes "
                                  f"and the source's is {len(before)}; a word patch changes no length.")
        wanted = {word.address: word for patch in expected for word in patch.words}
        touched: set = set()
        for address, word in sorted(wanted.items()):
            try:
                offset = ps2_elf.file_offset(segments, address)
                found = ps2_elf.read_word(after, segments, address)
                was = ps2_elf.read_word(before, segments, address)
            except ps2_elf.PnachError as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if was != word.original:
                return Verdict(False, f"Verification failed: the source ELF holds {_hex(was)} at "
                                      f"{_hex(address)}, not the {_hex(word.original)} the receipt names.")
            if found != word.replacement:
                return Verdict(False, f"Verification failed: the new ELF holds {_hex(found)} at "
                                      f"{_hex(address)}, not the {_hex(word.replacement)} the receipt names.")
            touched.update(range(offset, offset + 4))
        stray = [index for index in range(len(after))
                 if after[index] != before[index] and index not in touched]
        if stray:
            return Verdict(False, f"Verification failed: {len(stray)} byte(s) of the boot ELF "
                                  f"changed outside the {len(wanted)} declared word(s), the first "
                                  f"at file offset 0x{stray[0]:X}.")
        image = self._compare_images(source, destination, receipt)
        if image is not None:
            return image
        return Verdict(True,
                       f"{len(wanted)} word(s) written into {boot_after.get('boot_file')} on the new "
                       f"image; every other byte of the executable and of the image is identical to "
                       f"the source.",
                       {"result": "PASS", "words": len(wanted),
                        "elf_bytes": len(after), "declared_ranges": len(receipt.declared_ranges)})

    @staticmethod
    def _compare_images(source: Path, destination: Path, receipt: Receipt) -> Optional[Verdict]:
        """Every differing byte of the two images lies in a declared range, or a verdict says so."""

        allowed = [(rng.start, rng.end) for rng in receipt.declared_ranges]
        chunk = 8 * 1024 * 1024
        try:
            if source.stat().st_size != destination.stat().st_size:
                return Verdict(False, "Verification failed: the new image is not the size of the "
                                      "source; this writer never changes an image's length.")
            with open(source, "rb") as left, open(destination, "rb") as right:
                position = 0
                while True:
                    a = left.read(chunk)
                    b = right.read(chunk)
                    if not a and not b:
                        break
                    if len(a) != len(b):
                        return Verdict(False, "Verification failed: the two images stopped at "
                                              "different lengths.")
                    if a != b:
                        for index, pair in enumerate(zip(a, b)):
                            if pair[0] == pair[1]:
                                continue
                            at = position + index
                            if not any(start <= at < end for start, end in allowed):
                                return Verdict(False, f"Verification failed: image byte 0x{at:X} "
                                                      f"changed and lies in no declared range.")
                    position += len(a)
        except OSError as exc:
            return Verdict(False, f"Verification failed: {exc}")
        return None

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        elf = ps2_elf.build_synthetic_elf(synthetic_elf_words(), base_vaddr=SYNTHETIC_BASE)
        boot = (f"BOOT2 = cdrom0:\\{containers.BOOT_FILE};1\r\nVER = 1.00\r\n"
                f"VMODE = NTSC\r\n").encode("ascii")
        image = iso_lib.build_synthetic_iso(
            files=[
                (b"SYSTEM.CNF;1", boot),
                (f"{containers.BOOT_FILE};1".encode("ascii"), elf),
            ],
            sub_name=b"DATA",
            sub_files=[(b"GAMEDATA.DAT;1", bytes(2048))],
        )
        path = Path(work_dir) / "madden09-ps2-code-synthetic.iso"
        path.write_bytes(image)
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        """The real translation, on a synthetic ELF that carries the real originals."""

        return (Edit(PLAYBOOK_CAPS_PATCH_ID,
                     {"parameters": {"formations_cap": 30, "sets_cap": 130,
                                     "plays_cap": 400, "plays_per_set_cap": 120}},
                     note="conformance: the playbook editor caps, translated"),)


# --------------------------------------------------------------------------
# Command line and self-test
# --------------------------------------------------------------------------

def _lane() -> Madden09CodePatchLane:
    from . import IDENTITY  # this module's identity; imported here so the file stays a plain module

    return Madden09CodePatchLane(IDENTITY)


def selftest() -> int:
    """Prove the whole pipeline on a synthetic ELF; needs no game data."""

    import tempfile

    lane = _lane()
    failures: List[str] = []
    with tempfile.TemporaryDirectory() as work:
        room = Path(work)
        source = lane.synthetic_source(room)
        catalogue = lane.build_catalogue(source)
        if not catalogue.targets:
            failures.append("the catalogue named no patches")
        row = catalogue.target(PLAYBOOK_CAPS_PATCH_ID).raw
        if not row.get("sites_match"):
            failures.append("the synthetic ELF does not hold this lane's own original words")
        for patch in lane.patches():
            if patch.patch_id in TRANSLATIONS:
                continue
            try:
                lane.translation(patch.patch_id, {})
            except Refusal as exc:
                if "not mapped" not in str(exc):
                    failures.append(f"{patch.patch_id}: unexpected refusal {exc}")
            else:
                failures.append(f"{patch.patch_id}: a translation exists but was not declared")
        for bad in ({"formations_cap": 19}, {"plays_cap": MAX_CAP + 1},
                    {"sets_cap": True}, {"nonesuch": 40}, {}):
            try:
                lane.translation(PLAYBOOK_CAPS_PATCH_ID, bad)
            except Refusal:
                pass
            else:
                failures.append(f"{PLAYBOOK_CAPS_PATCH_ID}: accepted {bad!r}")
        edits = lane.conformance_edits(catalogue)
        recipe = lane.compose_recipe(edits)
        plan = lane.plan(source, recipe, catalogue)
        if len(plan.document["patches"][0]["words"]) != len(CAP_SITES):
            failures.append("the plan did not declare every cap site")
        out = room / "madden09.pnach"
        receipt = lane.build(source, out, recipe, catalogue)
        verdict = lane.verify(source, out, receipt)
        if not verdict.passed:
            failures.append(f"verify failed: {verdict.summary}")
        tampered = out.read_text(encoding="utf-8").replace(
            _hex(CAP_SITES[0].word_for(30)), _hex(CAP_SITES[0].word_for(31)))
        bad_file = room / "tampered.pnach"
        bad_file.write_text(tampered, encoding="utf-8", newline="\n")
        if lane.verify(source, bad_file, receipt).passed:
            failures.append("verify passed a tampered pnach")
        try:
            lane.build(source, out, recipe, catalogue)
        except Refusal:
            pass
        else:
            failures.append("build overwrote an existing destination")
        disc_recipe = dict(recipe)
        disc_recipe["deliver"] = "disc"
        disc = room / "madden09-patched.iso"
        disc_receipt = lane.build(source, disc, disc_recipe, catalogue)
        disc_verdict = lane.verify(source, disc, disc_receipt)
        if not disc_verdict.passed:
            failures.append(f"disc verify failed: {disc_verdict.summary}")
    for line in failures:
        print(f"FAIL {line}", file=sys.stderr)
    print("CODE_PATCH_SELFTEST %s patches=%d translations=%d sites=%d"
          % ("PASS" if not failures else "FAIL",
             len(PROPOSED_PATCHES) + len(TRANSLATIONS), len(TRANSLATIONS), len(CAP_SITES)))
    return 1 if failures else 0


def _run_recipe(lane: Madden09CodePatchLane, source: Path, recipe_path: Path,
                destination: Path) -> int:
    recipe = json.loads(Path(recipe_path).read_text(encoding="utf-8"))
    catalogue = lane.build_catalogue(source)
    plan = lane.plan(source, recipe, catalogue)
    print(f"PLAN delivery={plan.document['delivery']} crc={plan.document['crc']} "
          f"words={sum(len(row['words']) for row in plan.document['patches'])}")
    for row in plan.document["patches"]:
        for word in row["words"]:
            print(f"  {row['patch_id']:24s} {word['address']}  {word['original']} -> "
                  f"{word['replacement']}")
    receipt = lane.build(source, destination, recipe, catalogue)
    if receipt.document["delivery"] == "pnach":
        print("--- pnach ---")
        print(destination.read_text(encoding="utf-8"), end="")
        print("--- end ---")
    verdict = lane.verify(source, destination, receipt)
    print(f"VERIFY {'PASS' if verdict.passed else 'FAIL'} {verdict.summary}")
    return 0 if verdict.passed else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.code_patches",
        description="Madden NFL 09 (PS2) executable patches: catalogue, pnach and on-disc delivery.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--recipe", help="a recipe to plan, build and verify against --source")
    parser.add_argument("--destination", help="where the build writes (a .pnach, or a NEW .iso)")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the pipeline on a synthetic ELF; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if arguments.selftest:
        return selftest()
    if not arguments.source:
        parser.error("give --source DISC.iso, or --selftest")
    lane = _lane()
    if arguments.recipe:
        if not arguments.destination:
            parser.error("--recipe needs --destination")
        try:
            return _run_recipe(lane, Path(arguments.source), Path(arguments.recipe),
                               Path(arguments.destination))
        except Refusal as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    try:
        catalogue = lane.build_catalogue(Path(arguments.source))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    elf = document["elf"]
    sites = next((row.get("sites", []) for row in document["patches"]
                  if row["patch_id"] == PLAYBOOK_CAPS_PATCH_ID), [])
    print("CODE_PATCHES patches=%d mapped=%d edition=%s crc=%s sites_verified=%d/%d"
          % (len(document["patches"]), document["translations_available"],
             elf["edition"], elf["pcsx2_crc"],
             sum(1 for site in sites if site["matches"]), len(sites)))
    for site in sites:
        print(f"  {site['table']:16s} {site['address']}  {site['found']}  "
              f"{'MATCH' if site['matches'] else 'MISMATCH'}  cap={site['shipped_cap']}  "
              f"{site['disassembly']}")
    return 0


__all__ = ["CAPABILITY_ID", "CAP_PARAMETERS", "CAP_SITES", "CATALOG_SCHEMA", "CapSite",
           "DELIVERIES", "LANE_ID", "MAX_CAP", "MAX_IMMEDIATE", "Madden09CodePatchLane",
           "NOT_MAPPED", "PLAYBOOK_CAPS_PATCH_ID", "PROPOSED_PATCHES", "RECIPE_SCHEMA",
           "SECOND_LAYER_NOTE", "SIGN_EXTENSION_CAP", "SURFACE", "SYNTHETIC_BASE",
           "SYNTHETIC_WORDS", "TRANSLATIONS", "TRANSLATION_NOTES", "WRITE_SCHEMA",
           "check_cap_parameters", "playbook_caps_note", "proposed_patches",
           "selftest", "synthetic_elf_words", "translated_patches"]


if __name__ == "__main__":
    raise SystemExit(main())
