"""The rest of the PlayStation 2 disc surfaces, expressed on the game-module contract.

``__init__.py`` puts one shipped writer -- the uniform colour words -- on
:mod:`mod_editor.games.contract`.  This module does the same for the five other
on-disc writers and for the read-only disc inventory, so the whole game is
reachable through one vocabulary instead of through six bespoke tabs:

============================  ==============================================
lane                          what the user changes
============================  ==============================================
``menus.text_banks``          display strings inside the five text banks
``players.disc_roster``       names, jerseys and face shields in the rosters
``scripts.director_playbook`` formations and plays inside a playbook
``stadiums.position_lanes``   where a stadium's geometry sits
``audio.audo_exact_slot``     one AUDO sound, from the user's own WAV
``textures.disc_inventory``   nothing -- it lists what is on the disc
============================  ==============================================

Every lane here is an *adapter*.  The catalogue tool, the patcher and the
independent verifier under ``tools/`` are imported and called unchanged, the
way ``mod_editor/core/ps2_disc_studio_lanes.py`` calls them for the Qt studio;
what this module adds is the contract's shape -- :class:`Target` rows that
carry :class:`Field` descriptions so a generic editor can draw them, a plan
that declares byte ranges, a receipt the verifier can be handed back, and the
two things CI needs to prove a lane without game data: a retail-free synthetic
source and a known-good edit on it.

Two rules shape the odd corners below.

**A recipe is composed without the disc.**  ``compose_recipe`` sees the staged
edits and nothing else -- no source, no catalogue -- because that is the only
signature a shell can call while the user is still typing.  Two lanes want
more than that: the stadium patcher wants absolute vertex coordinates pinned
to a catalogue file's digest, and the text patcher likes an ``expect_sha256``
per string.  Both are resolved in ``plan``/``build``, which *do* have the
source and the catalogue, from a recipe that carries only what the user chose.
The stadium lane therefore composes offsets and names its own recipe schema;
the patcher's own schema is what ``build`` writes to disk for it.

**A receipt never carries what the disc said.**  The stadium receipt records
which lane moved and by how much, never the coordinates it moved from -- those
are the user's disc, not ours -- so ``verify`` re-derives them from the source
image, which is what an independent check should do anyway.

Standard library plus ``tools/`` only.  Qt is never imported, and the only
``mod_editor`` import at module level is the contract itself: this file is
loaded by every conformance run, on machines with no display.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
from typing import Any, Callable, Mapping, Optional, Sequence

from mod_editor.games.contract import (
    Catalogue,
    DeclaredRange,
    Edit,
    Field,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    require,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_audo_patch as audo_patch  # noqa: E402
import nfl2k5_ps2_audo_target_catalog as audo_catalog  # noqa: E402
import nfl2k5_ps2_audo_verify as audo_verify  # noqa: E402
import nfl2k5_ps2_disc_inventory as inventory_lib  # noqa: E402
import nfl2k5_ps2_disc_roster_patch as roster_patch  # noqa: E402
import nfl2k5_ps2_disc_roster_target_catalog as roster_catalog  # noqa: E402
import nfl2k5_ps2_disc_roster_verify as roster_verify  # noqa: E402
import nfl2k5_ps2_playbook_patch as playbook_patch  # noqa: E402
import nfl2k5_ps2_playbook_target_catalog as playbook_catalog  # noqa: E402
import nfl2k5_ps2_playbook_verify as playbook_verify  # noqa: E402
import nfl2k5_ps2_stadium_position_patch as stadium_patch  # noqa: E402
import nfl2k5_ps2_stadium_position_verify as stadium_verify  # noqa: E402
import nfl2k5_ps2_stadium_target_catalog as stadium_catalog  # noqa: E402
import nfl2k5_ps2_text_patch as text_patch  # noqa: E402
import nfl2k5_ps2_text_target_catalog as text_catalog  # noqa: E402
import nfl2k5_ps2_text_verify as text_verify  # noqa: E402
import nfl2k5_ps2_unif_color_target_catalog as colour_catalog  # noqa: E402
import nfl_txtr as txtr  # noqa: E402
import ps2_iso9660 as iso_lib  # noqa: E402
import spu_adpcm  # noqa: E402


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

#: Every exception a lane tool may raise for a bad input.  A lane catches this
#: tuple and re-raises the tool's own sentence as a :class:`Refusal`, so a
#: window, a worker and the conformance harness all have one thing to catch and
#: the wording stays the tool's.  ``AssertionError`` is in the list because the
#: verifiers raise their refusals through ``assert``-shaped helpers.
TOOL_ERRORS = (
    AssertionError,
    KeyError,
    OSError,
    TypeError,
    ValueError,
    struct.error,
)

#: The 32-byte resource wrapper every VC chunk on this disc starts with:
#: four-character kind, stored size, system bytes, video bytes, then the word
#: that is non-zero when the body is LZ-compressed.  Written here only to build
#: synthetic sources; the readers all parse it from the tools' own code.
_CHUNK_HEADER_SIZE = 0x20
_COMPRESSED = 0xFEEDBEEF


def _refuse(exc: BaseException) -> Refusal:
    """The tool's own sentence, never re-worded on its way up."""

    return Refusal(str(exc).strip() or exc.__class__.__name__)


def _run(action: Callable[[], Any]) -> Any:
    """Call a lane tool, turning anything it refuses into a :class:`Refusal`."""

    try:
        return action()
    except Refusal:
        raise
    except TOOL_ERRORS as exc:
        raise _refuse(exc) from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(document: Any) -> bytes:
    """Bytes, not text: LF everywhere, no platform newline question."""

    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _chunk(fourcc: bytes, body: bytes, compressed: bool = False) -> bytes:
    """One uncompressed VC resource chunk around ``body``, for synthetic sources."""

    header = bytearray(_CHUNK_HEADER_SIZE)
    header[0:4] = fourcc
    struct.pack_into("<IIII", header, 4, len(body), 0, 0, _COMPRESSED if compressed else 0)
    return bytes(header) + body


def _guard_destination(source: Path, destination: Path) -> None:
    """The two refusals every build makes before it opens anything."""

    require(
        destination.resolve() != source.resolve(),
        f"{destination} is the source image; a build writes a NEW image and never the source.",
    )
    require(
        not destination.exists(),
        f"destination {destination} already exists; refusing to overwrite an image",
    )


def _work(work_dir: Optional[Path]) -> "_Scratch":
    """A directory to stage recipe and catalogue files in, borrowed or made."""

    return _Scratch(work_dir)


class _Scratch:
    """``work_dir`` when the caller gave one, otherwise a directory we remove.

    The tools that take file paths rather than documents -- the playbook and
    stadium patchers -- need somewhere to put a recipe.  A caller that already
    has a scratch room keeps its files for inspection; one that does not gets a
    temporary directory that disappears with the ``with`` block.
    """

    def __init__(self, work_dir: Optional[Path]) -> None:
        self._given = Path(work_dir) if work_dir else None
        self._temporary: Optional[tempfile.TemporaryDirectory] = None

    def __enter__(self) -> Path:
        if self._given is not None:
            self._given.mkdir(parents=True, exist_ok=True)
            return self._given.resolve()
        self._temporary = tempfile.TemporaryDirectory(prefix="nfl2k5-ps2-lane-")
        return Path(self._temporary.name).resolve()

    def __exit__(self, *_exception: Any) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None


def _pack_bases(source: Path) -> dict[str, int]:
    """Each ``/VC_20919/N.`` pack's byte offset in the image, by ISO path."""

    image = iso_lib.open_image(str(source))
    bases: dict[str, int] = {}
    for letter, base, _size in inventory_lib.discover_packs(image):
        bases[f"/VC_20919/{letter}."] = int(base)
    return bases


# --------------------------------------------------------------------------
# Text banks
# --------------------------------------------------------------------------

class TextLane:
    """Display strings inside the fixed-allocation text banks, rewritten in place.

    A replacement may be shorter than the original or exactly as long, never
    longer: the disc's string pools have no spare bytes, so the budget a target
    quotes is the original string's own length.  Inline tokens such as
    ``|CROSS|`` draw glyphs and must survive the rewrite in the same order,
    which is why ``check_edit`` compares the token census rather than just the
    length.
    """

    lane_id = "menus.text_banks"
    capability_id = "nfl2k5ps2.menus.text_banks"
    surface = "menus"
    title = "Menu and display text"
    classification = "offline-writer-proved"
    recipe_schema = text_patch.SCHEMA
    validators = (
        "tools/validate_nfl2k5_ps2_text.sh",
        "tools/validate_nfl2k5_ps2_text.bat",
    )
    fixed_allocation = True

    # -- catalogue -----------------------------------------------------

    @staticmethod
    def limit_of(row: Mapping[str, Any]) -> int:
        """How many characters an allocation holds: its bytes, less the terminator."""

        return max(0, int(row["allocation_bytes"]) // 2 - 1)

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        if progress is not None:
            progress("Reading the text banks…")
        document = _run(lambda: text_catalog.build_catalog(str(source)))
        reasons = document.get("scope", {}).get("reason_codes", {})
        targets = []
        for row in document["strings"]:
            limit = self.limit_of(row)
            editable = bool(row.get("editable"))
            reason = "" if editable else str(
                reasons.get(row.get("reason_code", ""), row.get("reason_code", ""))
            )
            detail = [str(row.get("bank_kind", "")), f"{int(row.get('used_code_units', 0))} of {limit} characters"]
            references = int(row.get("reference_count", 1))
            if references > 1:
                detail.append(f"used by {references} records")
            tokens = list(row.get("tokens") or [])
            if tokens:
                detail.append("keeps " + " ".join(tokens))
            if not editable:
                detail.append(f"read-only: {reason}")
            help_text = (
                f"Up to {limit} characters — the original string's own length. "
                "This disc's pools have no spare bytes, so a longer replacement is refused."
            )
            if tokens:
                help_text += " Keep " + " ".join(tokens) + " exactly as they are; the engine draws a glyph there."
            targets.append(Target(
                key=str(row["selector"]),
                label=str(row.get("label") or row["selector"]),
                detail=" · ".join(piece for piece in detail if piece),
                budget=f"Up to {limit} characters (the original's own length)",
                searchable=" ".join([str(row.get("label", "")), str(row["selector"]),
                                     str(row.get("bank_kind", ""))]),
                raw=row,
                fields=(Field("new_text", "text", "Replacement text",
                              help_text, read_only=not editable),),
            ))
        return Catalogue(
            schema=document["schema"],
            lane_id=self.lane_id,
            source=str(source),
            targets=tuple(targets),
            document=document,
        )

    # -- editing -------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"new_text", "expect_sha256"})
        if unknown:
            return f"{target.key}: {', '.join(unknown)} is not something this lane writes; give new_text."
        if not target.raw.get("editable"):
            reason = str(target.raw.get("reason_code") or "its consumer is lookup, not display")
            return f"This string is read-only ({reason}); choose one of the editable strings."
        text = values.get("new_text")
        if not isinstance(text, str) or text == "":
            return "Type the replacement text; an empty string cannot be written."
        if "\x00" in text:
            return "The replacement may not contain a NUL character; remove it."
        limit = self.limit_of(target.raw)
        units = len(text.encode("utf-16le")) // 2
        if units > limit:
            return (f"{units} characters is {units - limit} over the budget of {limit}. The budget is "
                    f"the original string's own length; shorten the replacement to {limit}.")
        original = list(target.raw.get("tokens") or [])
        replacement = text_catalog.tokens_in(text)
        if replacement != original:
            if original:
                return ("Keep the inline tokens exactly as the original has them, in order: "
                        + " ".join(original) + ". The engine draws a glyph where each one sits.")
            return ("The replacement adds an inline token (" + " ".join(replacement)
                    + ") the original does not have; remove it.")
        if _sha256(text.encode("utf-16le")) == target.raw.get("text_sha256"):
            return "That is the text already there; change it or leave the string alone."
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: dict[str, Any] = {"selector": edit.target_key, "new_text": edit.values.get("new_text")}
            if edit.values.get("expect_sha256"):
                row["expect_sha256"] = edit.values["expect_sha256"]
            rows.append(row)
        return {"schema": self.recipe_schema, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    @staticmethod
    def _edits(recipe: Mapping[str, Any]) -> list:
        rows = recipe.get("edits")
        require(isinstance(rows, list) and rows, "a text recipe needs a non-empty 'edits' list")
        return list(rows)

    @staticmethod
    def _ranges(report: Mapping[str, Any]) -> tuple[DeclaredRange, ...]:
        return tuple(
            DeclaredRange(int(span["iso_byte_offset"]), int(span["length"]),
                          f"text:{pack['iso_path']}+0x{int(span['pack_offset']):x}")
            for pack in report.get("packs", [])
            for span in pack.get("replaced_ranges", [])
        )

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        report = _run(lambda: text_patch.patch(
            source_iso=str(source), destination_iso=None,
            edits=self._edits(recipe), dry_run=True))
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(str(item["selector"]) for item in report["edits"]),
            declared_ranges=self._ranges(report),
            document={
                "changed_byte_count": report["recipe"]["changed_byte_count"],
                "edits": report["edits"],
                "packs": [pack["iso_path"] for pack in report["packs"]],
            },
        )

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        source, destination = Path(source), Path(destination)
        _guard_destination(source, destination)
        report = _run(lambda: text_patch.patch(
            source_iso=str(source), destination_iso=str(destination), edits=self._edits(recipe)))
        return Receipt(
            schema=report["schema"],
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=self._ranges(report),
            # The verifier re-derives the whole claim from the two images and
            # the *recipe*; the patcher's report deliberately holds no
            # replacement text, so the recipe travels beside it.
            document=dict(report, recipe=dict(recipe)),
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        document = dict(receipt.document)
        recipe = dict(document.pop("recipe", {}))
        try:
            report = text_verify.verify(
                source_iso=str(source), destination_iso=str(destination), recipe=recipe,
                patch_report=document, iso_write_report=document.get("iso_write_report"))
        except TOOL_ERRORS as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        return Verdict(
            str(report.get("verdict", "")).upper() == "PASS",
            f"text verifier: {report.get('verdict', '?')} · {len(report.get('edits', []))} string(s) located · "
            f"{report.get('changed_byte_count', 0):,} bytes differ, exactly the edited allocations.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    #: Long enough to shorten, with one token string and one at the limit.
    SYNTHETIC_TEXTS = ("MENU", "Press |CROSS| to go", "Score %d", "OPTIONS", "OPT")

    def synthetic_source(self, work_dir: Path) -> Path:
        body = text_catalog.build_synthetic_strg_body(list(self.SYNTHETIC_TEXTS))
        image = colour_catalog.build_synthetic_iso(entries=[
            ("STRINGS.BIN", _chunk(b"STRG", body)),
            ("18H0.IFF", colour_catalog.unif_chunk(0xFFA29895, 0xFF272320)),
        ])
        path = Path(work_dir) / "nfl2k5-ps2-text-synthetic.iso"
        path.write_bytes(image)
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        for target in catalogue.targets:
            if target.raw.get("editable") and self.limit_of(target.raw) >= 4 and not target.raw.get("tokens"):
                return (Edit(target.key,
                             {"new_text": "HI", "expect_sha256": target.raw["text_sha256"]},
                             note="conformance"),)
        raise Refusal("the synthetic text bank carries no editable string; rebuild the fixture")


# --------------------------------------------------------------------------
# Disc roster
# --------------------------------------------------------------------------

#: The three face shields the packed equipment field encodes; the fourth value
#: is reserved and the writer refuses it.
FACE_SHIELDS = ("None", "Clear", "Dark")
#: What a picker or a spinner says when the user has not chosen anything.  A
#: text box can be left blank and a shell drops it, but a combo and a spinner
#: always have *some* value, so the two fields that are not text name their own
#: "leave it alone" reading rather than writing a default over the disc.
KEEP_CHOICE = "Keep"
KEEP_JERSEY = -1


class RosterLane:
    """Names, jerseys and face shields in the rosters the disc boots with.

    A name's budget is the bytes its own string already occupies, terminator
    included, so a longer name is refused rather than allowed to run into its
    neighbour.  Some slots cannot take a name at all -- an empty placeholder
    has no room, and a name shared by several records would change all of them
    -- and the catalogue says which, so the refusal names the reason.

    Only the boot roster is offered.  The catalogue tool decodes that one; the
    75 historic rosters are read from the disc on demand by the Qt studio, and
    a lane whose targets came from somewhere other than its own catalogue could
    not be pinned by a plan.
    """

    lane_id = "players.disc_roster"
    capability_id = "nfl2k5ps2.players.disc_roster"
    surface = "players_rosters"
    title = "Player names, numbers and face shields"
    classification = "offline-writer-proved"
    recipe_schema = roster_patch.RECIPE_SCHEMA
    validators = (
        "tools/validate_nfl2k5_ps2_disc_roster.sh",
        "tools/validate_nfl2k5_ps2_disc_roster.bat",
    )
    fixed_allocation = True

    NAME_FIELDS = ("first_name", "last_name")
    #: Every roster this lane offers lives in the disc's own boot roster.
    ROSTER = "boot"

    # -- catalogue -----------------------------------------------------

    @staticmethod
    def name_limit(player: Mapping[str, Any], field_name: str) -> int:
        return max(0, (int(player.get(field_name + "_capacity", 0)) - 2) // 2)

    def _fields(self, player: Mapping[str, Any]) -> tuple[Field, ...]:
        fields = []
        for name in self.NAME_FIELDS:
            label = name.replace("_", " ")
            writable = bool(player.get(name + "_writable"))
            if writable:
                limit = self.name_limit(player, name)
                help_text = (f"Up to {limit} characters — the bytes this name already occupies. "
                             "A name never grows into its neighbour, so a longer one is refused.")
            elif int(player.get(name + "_capacity", 0)) <= 2:
                help_text = "This slot is an empty placeholder with no room for a name."
            else:
                help_text = (f"This name is shared by {int(player.get(name + '_references', 0))} records; "
                             "rewriting it would change them all.")
            fields.append(Field(name, "text", label.title(), help_text, read_only=not writable))
        fields.append(Field("jersey_number", "int", "Jersey number",
                            f"A whole number from 0 to 99. Leave it at {KEEP_JERSEY} to keep the "
                            f"number the player already wears.",
                            minimum=KEEP_JERSEY, maximum=99))
        fields.append(Field("face_shield", "choice", "Face shield",
                            f"None, Clear or Dark; the reserved fourth value is refused. "
                            f"{KEEP_CHOICE} leaves the shield the player already has.",
                            choices=(KEEP_CHOICE,) + FACE_SHIELDS))
        return tuple(fields)

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        if progress is not None:
            progress("Reading the disc rosters…")
        document = _run(lambda: roster_catalog.build_catalog(str(source)))
        targets = []
        for player in document.get("players", []):
            first = str(player.get("first_name") or "")
            last = str(player.get("last_name") or "")
            name = f"{first} {last}".strip() or "(empty slot)"
            budgets = []
            for field_name in self.NAME_FIELDS:
                label = field_name.replace("_", " ")
                if player.get(field_name + "_writable"):
                    budgets.append(f"{label} up to {self.name_limit(player, field_name)} characters")
                else:
                    budgets.append(f"{label} not writable")
            targets.append(Target(
                key=f"{self.ROSTER}:{player['pool']}:{int(player['index'])}",
                label=f"{name} #{player.get('jersey_number', '?')}",
                detail=f"{str(player['pool']).replace('_', ' ')} {player['index']}",
                budget="; ".join(budgets) + "; jersey 0–99; face shield None/Clear/Dark",
                searchable=" ".join([first, last, str(player.get("jersey_number", "")),
                                     str(player["index"]), str(player["pool"])]),
                raw=player,
                fields=self._fields(player),
            ))
        return Catalogue(
            schema=document["schema"],
            lane_id=self.lane_id,
            source=str(source),
            targets=tuple(targets),
            document=document,
        )

    # -- editing -------------------------------------------------------

    @staticmethod
    def shield_value(value: Any) -> Optional[int]:
        """``"Clear"`` or ``1`` -> ``1``; "Keep", blank or anything else -> ``None``."""

        if isinstance(value, bool):
            return None
        if isinstance(value, int) and 0 <= value <= 2:
            return value
        if isinstance(value, str):
            for index, label in enumerate(FACE_SHIELDS):
                if value.strip().casefold() == label.casefold():
                    return index
        return None

    @staticmethod
    def _asked(values: Mapping[str, Any], key: str) -> Any:
        """The value the user actually asked for, or ``None`` for "leave it"."""

        value = values.get(key)
        if value in (None, ""):
            return None
        if key == "face_shield" and isinstance(value, str) and value.strip().casefold() == KEEP_CHOICE.casefold():
            return None
        if key == "jersey_number" and value == KEEP_JERSEY:
            return None
        return value

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        known = set(self.NAME_FIELDS) | {"jersey_number", "face_shield"}
        unknown = sorted(set(values) - known)
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane writes; "
                    "give a name, a jersey number or a face shield.")
        player = target.raw
        changes = 0
        for field_name in self.NAME_FIELDS:
            value = self._asked(values, field_name)
            if value is None:
                continue
            label = field_name.replace("_", " ")
            if not isinstance(value, str):
                return f"{label} must be text."
            if "\x00" in value:
                return f"{label} may not contain a NUL character; remove it."
            if not player.get(field_name + "_writable"):
                if int(player.get(field_name + "_capacity", 0)) <= 2:
                    return (f"This player's {label} slot is an empty placeholder with no room for a "
                            "name; choose a player whose name is already stored.")
                return (f"This player's {label} string is shared by "
                        f"{int(player.get(field_name + '_references', 0))} records, so rewriting it "
                        "would change another record too; choose a player with an unshared name.")
            limit = self.name_limit(player, field_name)
            units = len(value.encode("utf-16le")) // 2
            if units > limit:
                return (f"{label}: {units} characters is {units - limit} over the budget of {limit}; "
                        f"the name must fit the bytes the original occupies. Shorten it to {limit}.")
            if value == (player.get(field_name) or ""):
                return f"That is the {label} already there; change it or leave the field blank."
            changes += 1
        jersey = self._asked(values, "jersey_number")
        if jersey is not None:
            if isinstance(jersey, bool) or not isinstance(jersey, int) or not 0 <= jersey <= 99:
                return (f"Jersey number must be a whole number from 0 to 99, or {KEEP_JERSEY} to keep "
                        "the number the player already wears.")
            if jersey == player.get("jersey_number"):
                return f"The jersey is already {jersey}; choose another number or leave it as it is."
            changes += 1
        shield = self._asked(values, "face_shield")
        if shield is not None:
            if self.shield_value(shield) is None:
                return (f"Face shield must be None, Clear or Dark, or {KEEP_CHOICE} to leave it; "
                        "the reserved fourth value is refused.")
            changes += 1
        if not changes:
            return "Change at least one of first name, last name, jersey number or face shield."
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            # A key the lane does not recognise is carried through as it stands
            # rather than refused here: composing happens while the user is
            # still typing, and the patcher owns the sentence that names what a
            # selector must look like.  ``plan`` is where it is refused.
            _roster, _, rest = str(edit.target_key).partition(":")
            pool, _, index = rest.rpartition(":")
            row: dict[str, Any] = {"pool": pool, "player": int(index) if index.isdigit() else 0}
            for field_name in self.NAME_FIELDS:
                value = self._asked(edit.values, field_name)
                if value is not None:
                    row[field_name] = value
            jersey = self._asked(edit.values, "jersey_number")
            if jersey is not None:
                row["jersey_number"] = int(jersey)
            shield = self._asked(edit.values, "face_shield")
            if shield is not None:
                row["face_shield"] = self.shield_value(shield)
            rows.append(row)
        return {"schema": self.recipe_schema, "roster": self.ROSTER, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    @staticmethod
    def _parsed(recipe: Mapping[str, Any]) -> dict:
        return _run(lambda: roster_patch.parse_recipe(dict(recipe)))

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        parsed = self._parsed(recipe)
        prepared = _run(lambda: roster_patch.plan(Path(source), parsed, dict(catalogue.document)))
        edits = prepared["edits"]
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(f"{self.ROSTER}:{item['pool']}:{int(item['player'])}" for item in edits),
            declared_ranges=tuple(
                DeclaredRange(int(item["offset_in_iso"]), int(item["span_size"]),
                              f"roster_{item['kind']}:{item['pool']}:{item['player']}")
                for item in edits
            ),
            document={
                "roster": prepared["roster"],
                "edits": [{key: value for key, value in item.items() if key != "replacement"}
                          for item in edits],
            },
        )

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        source, destination = Path(source), Path(destination)
        _guard_destination(source, destination)
        parsed = self._parsed(recipe)
        report = _run(lambda: roster_patch.apply(
            source, destination, parsed,
            pinned_catalog=dict(catalogue.document), work_dir=work_dir))
        return Receipt(
            schema=report["schema"],
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=tuple(
                DeclaredRange(int(item["start"]), int(item["length"]), str(item["reason"]))
                for item in report["declared_ranges"]
            ),
            document=report,
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = roster_verify.verify(Path(source), Path(destination), dict(receipt.document))
        except TOOL_ERRORS as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        return Verdict(
            str(report.get("result", "")).upper() == "PASS",
            f"roster verifier: {report.get('result', '?')} · {report.get('edits_checked', 0)} edit(s) checked · "
            f"{report.get('rost_resources_decoded', 0)} ROST resource(s) decoded · "
            f"{report.get('unchanged_bytes_compared', 0):,} unchanged bytes compared.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "nfl2k5-ps2-roster-synthetic.iso"
        path.write_bytes(roster_catalog.build_synthetic_iso())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        for target in catalogue.targets:
            if target.raw.get("first_name_writable") and self.name_limit(target.raw, "first_name") >= 3:
                return (Edit(target.key, {"first_name": "Ann", "face_shield": "Dark"}, note="conformance"),)
        raise Refusal("the synthetic roster carries no writable name slot; rebuild the fixture")


# --------------------------------------------------------------------------
# Playbooks
# --------------------------------------------------------------------------

#: The Xbox writer's own bound on a formation or play name, restated here so
#: the inline check can quote it before the patcher is ever called.
MAX_CUSTOM_NAME_CHARS = 40


class PlaybooksLane:
    """New formations and plays inside a playbook, cloned from a donor already in it.

    A book is fixed-capacity -- 50 formations, 270 plays, 3,500 nodes -- and
    fixed-allocation on the disc, so an addition is only possible where the
    book has headroom.  What the writer takes is therefore a *donor* to clone
    and a name to give the clone, not a play drawn from scratch: everything the
    engine needs beyond the name and the eleven slot positions is copied from a
    play the book already validates.
    """

    lane_id = "scripts.director_playbook"
    capability_id = "nfl2k5ps2.scripts.director_playbook"
    surface = "scripts_config"
    title = "Playbook formations and plays"
    classification = "offline-writer-proved"
    recipe_schema = playbook_patch.SCHEMA
    validators = (
        "tools/validate_nfl2k5_ps2_playbook.sh",
        "tools/validate_nfl2k5_ps2_playbook.bat",
    )
    fixed_allocation = True

    # -- catalogue -----------------------------------------------------

    @staticmethod
    def _fields(book: Mapping[str, Any]) -> tuple[Field, ...]:
        formations = max(0, int(book.get("formations", 0)))
        plays = max(0, int(book.get("plays", 0)))
        return (
            Field("donor_formation_index", "int", "Donor formation",
                  f"Which of this book's {formations} formations the new one is cloned from.",
                  minimum=0, maximum=max(0, formations - 1)),
            Field("donor_play_index", "int", "Donor play",
                  f"Which of this book's {plays} plays the new one is cloned from.",
                  minimum=0, maximum=max(0, plays - 1)),
            Field("custom_name", "text", "Name for the new play",
                  f"1 to {MAX_CUSTOM_NAME_CHARS} printable ASCII characters."),
            Field("create", "choice", "What to create",
                  "A formation cloned from the donor formation, a play cloned from the donor play, "
                  "or both.",
                  choices=("play", "formation", "both")),
        )

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        if progress is not None:
            progress("Reading the playbooks…")
        document = _run(lambda: playbook_catalog.build(str(source)))
        targets = []
        for book in document["books"]:
            at_cap = " · AT THE PLAY CAP" if book.get("at_play_capacity") else ""
            targets.append(Target(
                key=str(book["book_id"]),
                label=str(book.get("book_name") or book["book_id"]),
                detail=(f"{book.get('formations', 0)}/50 formations · {book.get('plays', 0)}/270 plays · "
                        f"{book.get('nodes', 0):,} nodes{at_cap}"),
                budget=(f"Room for {book.get('formation_headroom', 0)} more formations, "
                        f"{book.get('play_headroom', 0)} more plays and "
                        f"{book.get('node_headroom', 0):,} more nodes; names up to "
                        f"{MAX_CUSTOM_NAME_CHARS} printable ASCII characters"),
                searchable=f"{book.get('book_name', '')} {book['book_id']}",
                raw=book,
                fields=self._fields(book),
            ))
        return Catalogue(
            schema=document["schema"],
            lane_id=self.lane_id,
            source=str(source),
            targets=tuple(targets),
            document=document,
        )

    # -- editing -------------------------------------------------------

    @staticmethod
    def clean_name(value: Any) -> Optional[str]:
        """The writer's own rule for a custom name, restated for the inline check."""

        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise Refusal("A custom name must be text.")
        name = value.strip()
        if not 1 <= len(name) <= MAX_CUSTOM_NAME_CHARS:
            raise Refusal(f"A custom name must be 1 through {MAX_CUSTOM_NAME_CHARS} characters.")
        if any(ord(character) < 0x20 or ord(character) > 0x7E for character in name):
            raise Refusal("A custom name may use printable ASCII only.")
        return name

    @staticmethod
    def _wanted(values: Mapping[str, Any]) -> tuple[bool, bool]:
        """``(formation, play)``: which of the two the user asked for."""

        choice = str(values.get("create") or "play").strip().casefold()
        return choice in ("formation", "both"), choice in ("play", "both")

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        known = {"donor_formation_index", "donor_play_index", "custom_name", "create"}
        unknown = sorted(set(values) - known)
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane writes; "
                    "choose a donor, a name and what to create.")
        choice = str(values.get("create") or "play").strip().casefold()
        if choice not in ("play", "formation", "both"):
            return "Choose what to create: a play, a formation, or both."
        formation, play = self._wanted(values)
        book = target.raw
        if formation and int(book.get("formation_headroom", 0)) < 1:
            return (f"This book holds {book.get('formations', 0)} of 50 formations and can take "
                    f"{book.get('formation_headroom', 0)} more; adding one is refused. "
                    "Choose a book with room.")
        if play and int(book.get("play_headroom", 0)) < 1:
            return (f"This book holds {book.get('plays', 0)} of 270 plays and can take "
                    f"{book.get('play_headroom', 0)} more; adding one is refused. "
                    "Choose a book with room.")
        try:
            self.clean_name(values.get("custom_name"))
        except Refusal as exc:
            return f"Name: {exc}"
        for key, count, what in (("donor_formation_index", int(book.get("formations", 0)), "formation"),
                                 ("donor_play_index", int(book.get("plays", 0)), "play")):
            value = values.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < max(count, 1):
                return (f"The donor {what} must be one of this book's {count}; "
                        f"choose a number from 0 to {max(count - 1, 0)}.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            formation, play = self._wanted(edit.values)
            name = self.clean_name(edit.values.get("custom_name"))
            row: dict[str, Any] = {"book_id": str(edit.target_key)}
            if formation:
                entry: dict[str, Any] = {"donor_formation_index": int(edit.values.get("donor_formation_index") or 0)}
                if name:
                    entry["custom_name"] = name
                row["formations"] = [entry]
            if play:
                entry = {"donor_play_index": int(edit.values.get("donor_play_index") or 0)}
                if name:
                    entry["custom_name"] = name
                row["plays"] = [entry]
            require(formation or play, f"{edit.target_key}: choose a play, a formation, or both.")
            rows.append(row)
        return {"schema": self.recipe_schema, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    def _parsed(self, recipe: Mapping[str, Any], room: Path) -> list:
        """The patcher's own parse of the recipe; it reads a file, so we write one."""

        path = room / "playbook-recipe.json"
        path.write_bytes(_json_bytes(dict(recipe)))
        return _run(lambda: playbook_patch.load_recipe(path))

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        with _work(None) as room:
            parsed = self._parsed(recipe, room)
            compiled = _run(lambda: playbook_patch.compile_edits(Path(source), parsed))
        packs = {item["target"].pack.letter for item in compiled}
        require(len(packs) == 1,
                f"this tool patches one pack per run; the recipe spans {len(packs)}. "
                "Build the books in one pack first, then the others.")
        rows = []
        ranges = []
        for item in compiled:
            base = int(item["target"].absolute_offset)
            for low, high in item["changed_ranges"]:
                ranges.append(DeclaredRange(base + int(low), int(high) - int(low),
                                            f"playbook:{item['target'].id_text}"))
            rows.append({"book_id": item["target"].id_text,
                         "before": item["before"], "after": item["after"],
                         "changed_byte_count": item["changed_byte_count"]})
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(row["book_id"] for row in rows),
            declared_ranges=tuple(ranges),
            document={"books": rows,
                      "changed_byte_count": sum(row["changed_byte_count"] for row in rows)},
        )

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        source, destination = Path(source), Path(destination)
        _guard_destination(source, destination)
        with _work(work_dir) as room:
            parsed = self._parsed(recipe, room)
            report = _run(lambda: playbook_patch.patch(source, parsed, destination, workdir=room))
        return Receipt(
            schema=report["schema"],
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=tuple(
                DeclaredRange(int(item["absolute_offset"]) + int(low), int(high) - int(low),
                              f"playbook:{item['book_id']}")
                for item in report["play_edits"]
                for low, high in item["changed_ranges"]
            ),
            document=report,
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = playbook_verify.verify(Path(source), Path(destination), dict(receipt.document))
        except TOOL_ERRORS as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        return Verdict(
            str(report.get("verdict", "")).upper() == "PASS",
            f"playbook verifier: {report.get('verdict', '?')} · {report.get('declared_edits', 0)} book(s) checked · "
            f"{report.get('changed_byte_total', 0):,} bytes changed in "
            f"{len(report.get('changed_ranges', []))} range(s) · "
            f"{report.get('play_resources_found', 0)} book(s) found.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "nfl2k5-ps2-playbook-synthetic.iso"
        path.write_bytes(_synthetic_playbook_iso())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        for target in catalogue.targets:
            if int(target.raw.get("play_headroom", 0)) >= 1 and int(target.raw.get("plays", 0)) >= 1:
                return (Edit(target.key,
                             {"create": "play", "donor_play_index": 0, "custom_name": "SMASH"},
                             note="conformance"),)
        raise Refusal("the synthetic playbook has no room for another play; rebuild the fixture")


# --------------------------------------------------------------------------
# Stadium position lanes
# --------------------------------------------------------------------------

def binary32(value: float) -> float:
    """The nearest binary32 to ``value``; the patcher refuses anything else."""

    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


class StadiumLane:
    """Move every vertex of one catalogued stadium position lane by an offset.

    Vertex count and topology never change: the lane's coordinates are read
    from the user's disc, shifted, written back into the same slots and the
    scene is recompressed into the exact span it already owns.  Whether the
    recompressed scene *fits* that span is only decided during the build --
    the retail packer left between 0 and 16 spare bytes per scene -- and a
    refusal there leaves no image behind.

    The recipe this lane composes carries offsets, not coordinates.  That is
    both what a shell can compose without the disc and what keeps the user's
    own geometry out of every document we write down: ``plan`` and ``build``
    resolve the offsets against the source image into the patcher's own
    ``positions`` recipe, and ``verify`` re-derives the same thing.
    """

    lane_id = "stadiums.position_lanes"
    capability_id = "nfl2k5ps2.stadiums.position_lanes"
    surface = "stadiums_fields"
    title = "Stadium geometry position lanes"
    classification = "offline-writer-proved"
    #: Offsets, not coordinates -- see the class docstring.  ``build`` writes
    #: the patcher's own ``nfl2k5_ps2_stadium_position_recipe/v1`` from this.
    recipe_schema = "nfl2k5_ps2_stadium_offset_recipe/v1"
    validators = (
        "tools/validate_nfl2k5_ps2_stadium_position.sh",
        "tools/validate_nfl2k5_ps2_stadium_position.bat",
    )
    fixed_allocation = True

    AXES = ("dx", "dy", "dz")

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        if progress is not None:
            progress("Walking the disc for stadium scenes…")
        document = _run(lambda: stadium_catalog.catalog(str(source), scan=True))
        scenes = document.get("scenes", [])
        targets = []
        for row in document.get("targets", []):
            shape = row.get("shape", {})
            position = row.get("position", {})
            count = int(position.get("vertex_count", 0))
            shared = int(row.get("payload_span_target_count", 1))
            index = int(row.get("scene_index", 0))
            identity = scenes[index]["identity"] if index < len(scenes) else {}
            detail = [f"{count} vertices", f"batch {row.get('batch', {}).get('index')}",
                      f"entry {identity.get('entry_index')} chunk {identity.get('chunk_index')}"]
            if shared > 1:
                detail.append(f"span shared by {shared} targets")
            help_text = (f"Centimetres added to every one of this lane's {count} vertices, "
                         "rounded to the nearest binary32 the disc can store.")
            targets.append(Target(
                key=str(row["target_id"]),
                label=f"{shape.get('name') or 'shape'} {shape.get('index')} · "
                      f"lane {position.get('lane_ordinal_within_batch', 0)}",
                detail=" · ".join(str(piece) for piece in detail if piece),
                budget=f"Exactly {count} vertices; x, y and z offsets are added to every one",
                searchable=f"{row['target_id']} {shape.get('name', '')} {count}",
                raw=row,
                fields=tuple(
                    Field(axis, "float", f"Move {axis[-1].upper()} by", help_text)
                    for axis in self.AXES
                ),
            ))
        return Catalogue(
            schema=document["schema"],
            lane_id=self.lane_id,
            source=str(source),
            targets=tuple(targets),
            document=document,
        )

    # -- editing -------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - set(self.AXES))
        if unknown:
            return f"{target.key}: {', '.join(unknown)} is not an axis this lane moves; give dx, dy or dz."
        offsets = []
        for axis in self.AXES:
            value = values.get(axis, 0.0)
            if isinstance(value, bool):
                return f"{axis} must be a number."
            try:
                number = float(value)
            except (TypeError, ValueError):
                return f"{axis} must be a number."
            if not math.isfinite(number):
                return f"{axis} must be a finite number."
            offsets.append(number)
        if all(offset == 0.0 for offset in offsets):
            return "Enter an x, y or z offset other than zero; moving nothing is refused as a no-op."
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: dict[str, Any] = {"target_id": str(edit.target_key)}
            for axis in self.AXES:
                row[axis] = binary32(float(edit.values.get(axis, 0.0) or 0.0))
            rows.append(row)
        return {"schema": self.recipe_schema, "edits": rows}

    # -- resolving offsets into the patcher's own recipe ----------------

    @staticmethod
    def _offsets(recipe: Mapping[str, Any]) -> list[dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == StadiumLane.recipe_schema,
                f"a stadium recipe must carry schema {StadiumLane.recipe_schema}")
        rows = recipe.get("edits")
        require(isinstance(rows, list) and rows, "a stadium recipe needs a non-empty 'edits' list")
        out = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("target_id"), str)
                    and row["target_id"].strip(),
                    f"edit {number} must name the position lane it moves in 'target_id'")
            require(set(row) <= {"target_id"} | set(StadiumLane.AXES),
                    f"edit {number} carries a key this lane does not read; give target_id, dx, dy and dz")
            out.append(dict(row))
        return out

    @staticmethod
    def positions_of(decoded: bytes, row: Mapping[str, Any]) -> list[tuple[float, float, float]]:
        payload = row["position"]["payload"]
        count = int(row["position"]["vertex_count"])
        start = int(payload["offset"])
        return [struct.unpack_from("<3f", decoded, start + index * 16) for index in range(count)]

    def _catalogue_file(self, room: Path, catalogue: Catalogue) -> tuple[Path, dict]:
        """The catalogue as a file, because ``load_catalog`` pins its digest."""

        path = room / "stadium-catalogue.json"
        path.write_bytes(stadium_catalog.canonical_json(dict(catalogue.document)))
        return path, _run(lambda: stadium_patch.load_catalog(str(path)))

    def _resolved(self, source: Path, recipe: Mapping[str, Any],
                  loaded: Mapping[str, Any]) -> tuple[dict, bytes]:
        """The patcher's own recipe -- absolute positions, catalogue pinned -- and the scene.

        The decoded scene comes back with it because both the plan's byte
        count and the patcher's own dry run want it, and decoding it twice
        would mean reading and decompressing the user's image twice.
        """

        rows = self._offsets(recipe)
        scene_indices = set()
        for row in rows:
            target = loaded["rows"].get(str(row["target_id"]))
            require(target is not None,
                    f"{row['target_id']} is not a lane this disc's catalogue names; "
                    "rebuild the catalogue for this image.")
            scene_indices.add(int(target.get("scene_index", 0)))
        require(len(scene_indices) == 1,
                f"one build moves lanes inside one scene; this recipe spans {len(scene_indices)}. "
                "Stage the second scene's lanes as their own build.")
        decoded = self._decode_scene(source, loaded, scene_indices.pop())
        edits = []
        for row in rows:
            target = loaded["rows"][str(row["target_id"])]
            deltas = [binary32(float(row.get(axis, 0.0) or 0.0)) for axis in self.AXES]
            positions = [
                [binary32(value + delta) for value, delta in zip(vertex, deltas)]
                for vertex in self.positions_of(decoded, target)
            ]
            edits.append({"target_id": str(row["target_id"]), "positions": positions})
        return ({"schema": stadium_patch.RECIPE_SCHEMA,
                 "catalog": {"schema": stadium_catalog.SCHEMA, "sha256": loaded["sha256"]},
                 "edits": edits},
                decoded)

    @staticmethod
    def _decode_scene(source: Path, loaded: Mapping[str, Any], scene_index: int) -> bytes:
        """The scene's decoded buffer, read from the user's own image and never kept."""

        scenes = loaded["scenes"]
        require(0 <= scene_index < len(scenes), f"scene {scene_index} is not in this catalogue.")
        identity = scenes[scene_index]["identity"]
        image = iso_lib.open_image(str(source))
        packs = inventory_lib.discover_packs(image)
        archive = inventory_lib.VirtualPacks(str(source), packs)
        archive.open()
        try:
            _outer, table = _run(lambda: inventory_lib.read_outer_table(archive))
            chunk = _run(lambda: stadium_patch._locate_chunk(archive, table, identity))
            span = _run(lambda: archive.read(chunk["virtual_offset"], chunk["span_size"]))
        finally:
            archive.close()
        decoded, _info = _run(lambda: txtr.decode_chunk(
            span, txtr.parse_chunks(span, allow_trailing=True)[0]))
        require(_sha256(decoded[:int(identity["system_bytes"])]) == identity["system_sha256"],
                "the scene's system buffer differs from the catalogued one; rebuild the catalogue "
                "for this image.")
        return decoded

    def _declared(self, source: Path, report: Mapping[str, Any]) -> tuple[DeclaredRange, ...]:
        """The chunk's span in image coordinates: the whole recompressed scene."""

        bases = _pack_bases(source)
        ranges = []
        for pack in report.get("packs", []):
            base = bases.get(str(pack["iso_path"]))
            require(base is not None, f"pack {pack['iso_path']} is not in this image.")
            ranges.append(DeclaredRange(base + int(pack["pack_offset"]), int(pack["bytes_spliced"]),
                                        f"stadium:{pack['iso_path']}"))
        return tuple(ranges)

    # -- plan / build / verify -----------------------------------------

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        source = Path(source)
        with _work(None) as room:
            _path, loaded = self._catalogue_file(room, catalogue)
            resolved, decoded = self._resolved(source, recipe, loaded)
            parsed = self._write_and_load(room, resolved, loaded)
            edited, written = _run(lambda: stadium_patch.apply_positions(decoded, parsed["edits"]))
        changed = sum(1 for left, right in zip(decoded, edited) if left != right)
        chunk = self._chunk_span(source, loaded, parsed["identity"])
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(str(item["target_id"]) for item in written),
            declared_ranges=(DeclaredRange(chunk[0], chunk[1], "stadium:scene span"),),
            document={
                "edits": [{"target_id": item["target_id"], "vertex_count": item["vertex_count"],
                           "written_bytes": sum(high - low for low, high in item["ranges"])}
                          for item in written],
                "decoded_changed_bytes": changed,
                "note": ("Whether the recompressed scene fits the fixed span it owns is decided "
                         "during the build; a refusal there leaves no image behind."),
            },
        )

    @staticmethod
    def _write_and_load(room: Path, resolved: Mapping[str, Any], loaded: Mapping[str, Any]) -> dict:
        path = room / "stadium-recipe.json"
        path.write_bytes(stadium_catalog.canonical_json(dict(resolved)))
        return _run(lambda: stadium_patch.load_recipe(str(path), loaded))

    @staticmethod
    def _chunk_span(source: Path, loaded: Mapping[str, Any], identity: Mapping[str, Any]) -> tuple[int, int]:
        """``(iso offset, size)`` of the scene chunk a build rewrites."""

        image = iso_lib.open_image(str(source))
        packs = inventory_lib.discover_packs(image)
        archive = inventory_lib.VirtualPacks(str(source), packs)
        archive.open()
        try:
            _outer, table = _run(lambda: inventory_lib.read_outer_table(archive))
            chunk = _run(lambda: stadium_patch._locate_chunk(archive, table, identity))
        finally:
            archive.close()
        virtual = int(chunk["virtual_offset"])
        cursor = 0
        for _letter, base, size in packs:
            if cursor <= virtual < cursor + size:
                return base + (virtual - cursor), int(chunk["span_size"])
            cursor += size
        raise Refusal("the scene's chunk is not inside any pack on this image.")

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        source, destination = Path(source), Path(destination)
        _guard_destination(source, destination)
        with _work(work_dir) as room:
            catalogue_path, loaded = self._catalogue_file(room, catalogue)
            resolved, _decoded = self._resolved(source, recipe, loaded)
            recipe_path = room / "stadium-recipe.json"
            recipe_path.write_bytes(stadium_catalog.canonical_json(dict(resolved)))
            report = _run(lambda: stadium_patch.patch(
                str(source), str(catalogue_path), str(recipe_path), str(destination)))
        return Receipt(
            schema=report["schema"],
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=self._declared(source, report),
            # The offsets, never the coordinates: a receipt records what moved
            # and by how much, not where the user's disc had it.
            document=dict(report, offset_recipe=dict(recipe)),
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Re-derive the whole claim from the two images and the receipt's offsets.

        The catalogue is rebuilt from the source rather than trusted from the
        build, and it must come out as the digest the receipt pinned -- a disc
        that has moved since the build is a failed verification, not a pass on
        a stale claim.  The coordinates are then re-derived the same way the
        build derived them, because the receipt deliberately does not carry them.
        """

        source, destination = Path(source), Path(destination)
        try:
            with _work(None) as room:
                catalogue_path = room / "stadium-catalogue.json"
                document = _run(lambda: stadium_catalog.catalog(str(source), scan=True))
                catalogue_path.write_bytes(stadium_catalog.canonical_json(document))
                loaded = _run(lambda: stadium_patch.load_catalog(str(catalogue_path)))
                pinned = str(receipt.document.get("catalog", {}).get("sha256", ""))
                require(not pinned or pinned == loaded["sha256"],
                        "the source image no longer catalogues to the digest this build pinned; "
                        "the disc changed after the build, so nothing here can be verified.")
                resolved, _decoded = self._resolved(
                    source, receipt.document.get("offset_recipe", {}), loaded)
                recipe_path = room / "stadium-recipe.json"
                recipe_path.write_bytes(stadium_catalog.canonical_json(resolved))
                report = stadium_verify.verify(
                    str(source), str(destination), str(catalogue_path), str(recipe_path))
        except Refusal as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        except TOOL_ERRORS as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        decoded = report.get("decoded", {})
        return Verdict(
            str(report.get("verdict", "")).upper() == "PASS",
            f"stadium verifier: {report.get('verdict', '?')} · {decoded.get('changed_bytes', 0):,} decoded "
            f"bytes changed in {decoded.get('changed_ranges', 0)} range(s), every one inside a declared "
            f"lane · wrapper identical: {report.get('chunk', {}).get('wrapper_identical')}.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "nfl2k5-ps2-stadium-synthetic.iso"
        path.write_bytes(stadium_patch.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        if not catalogue.targets:
            raise Refusal("the synthetic disc carries no stadium scene; rebuild the fixture")
        return (Edit(catalogue.targets[0].key, {"dx": 0.0, "dy": 400.0, "dz": 0.0}, note="conformance"),)


# --------------------------------------------------------------------------
# AUDO sounds
# --------------------------------------------------------------------------

class AudioLane:
    """One standalone AUDO sound, replaced from the user's own 16-bit PCM WAV.

    A slot never grows.  The WAV is encoded to SPU-ADPCM and fitted to the byte
    count the slot already owns; a longer sound is refused with the slot's exact
    capacity in seconds, and a shorter one is followed by filler blocks the SPU
    never reaches.  A WAV at another sample rate is resampled to the slot's;
    a WAV with the wrong channel count is refused, because a mono slot has
    nowhere to put a second plane.
    """

    lane_id = "audio.audo_exact_slot_replace"
    capability_id = "nfl2k5ps2.audio.audo_exact_slot_replace"
    surface = "audio"
    title = "Menu and stadium sounds"
    classification = "runtime-proved"
    recipe_schema = audo_patch.RECIPE_SCHEMA
    validators = (
        "tools/validate_nfl2k5_ps2_audo.sh",
        "tools/validate_nfl2k5_ps2_audo.bat",
    )
    fixed_allocation = True

    # -- catalogue -----------------------------------------------------

    @staticmethod
    def capacity_seconds(slot: Mapping[str, Any]) -> float:
        rate = int(slot.get("sample_rate", 0)) or 1
        return int(slot.get("max_frames", 0)) / rate

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        if progress is not None:
            progress("Reading the sound slots…")
        document = _run(lambda: audo_catalog.build(str(source)))
        targets = []
        for slot in document.get("slots", []):
            seconds = self.capacity_seconds(slot)
            channels = "stereo" if int(slot.get("channels", 1)) == 2 else "mono"
            shared = "" if slot.get("unique_name") else " · shared name"
            targets.append(Target(
                key=str(slot["slot_id"]),
                label=str(slot.get("name") or slot["slot_id"]),
                detail=f"{channels} · {slot.get('sample_rate')} Hz · up to {seconds:.2f} s{shared}",
                budget=(f"Up to {seconds:.2f} s ({int(slot.get('max_frames', 0)):,} frames at "
                        f"{slot.get('sample_rate')} Hz), {channels} 16-bit PCM WAV"),
                searchable=f"{slot.get('name', '')} {slot['slot_id']} {channels} {slot.get('sample_rate')}",
                raw=slot,
                fields=(Field("wav", "wav", "Replacement sound",
                              f"A {channels} 16-bit PCM WAV no longer than {seconds:.2f} s. "
                              "Another sample rate is resampled to this slot's; a longer sound is "
                              "refused, because the slot never grows."),),
            ))
        return Catalogue(
            schema=document["schema"],
            lane_id=self.lane_id,
            source=str(source),
            targets=tuple(targets),
            document=document,
        )

    # -- editing -------------------------------------------------------

    def describe_wav(self, target: Target, wav_path: Path) -> dict:
        """Frames, seconds and fit for one WAV against one slot."""

        path = Path(wav_path)
        require(not path.is_symlink(), f"{path}: refusing to read a replacement through a symlink")
        require(path.is_file(), f"{path}: not a regular file")
        wav = _run(lambda: audo_patch.parse_wav(path.read_bytes()))
        slot = target.raw
        frames = int(wav["frames"])
        rate = int(slot["sample_rate"])
        if int(wav["rate"]) != rate:
            frames = max(1, int(math.floor(frames * rate / int(wav["rate"]))))
        return {"rate": int(wav["rate"]), "channels": int(wav["channels"]),
                "source_frames": int(wav["frames"]), "frames": frames, "seconds": frames / rate,
                "capacity_seconds": self.capacity_seconds(slot),
                "fits": frames <= int(slot["max_frames"]),
                "resampled": int(wav["rate"]) != rate}

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"wav"})
        if unknown:
            return f"{target.key}: {', '.join(unknown)} is not something this lane takes; choose a WAV."
        wav = values.get("wav")
        if not wav:
            return "Choose a WAV file for this slot."
        try:
            info = self.describe_wav(target, Path(str(wav)))
        except Refusal as exc:
            return str(exc)
        slot = target.raw
        if info["channels"] != int(slot["channels"]):
            want = "mono" if int(slot["channels"]) == 1 else "stereo"
            return (f"{slot.get('name')} is a {want} slot but the WAV has {info['channels']} channel(s); "
                    f"supply {want} audio.")
        if not info["fits"]:
            return (f"Your WAV is {info['seconds']:.2f} s at {slot['sample_rate']} Hz but the slot holds "
                    f"{info['capacity_seconds']:.2f} s ({int(slot['max_frames']):,} frames). This writer "
                    "never grows a slot; shorten the audio or choose a slot with more room.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            wav = edit.values.get("wav")
            require(bool(wav), f"{edit.target_key}: choose a WAV file for this slot.")
            rows.append({"slot": str(edit.target_key), "wav": str(Path(str(wav)).resolve())})
        return {"schema": self.recipe_schema, "replacements": rows}

    # -- plan / build / verify -----------------------------------------

    def _prepared(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> dict:
        rows = recipe.get("replacements")
        require(isinstance(rows, list) and rows, "an audio recipe needs a non-empty 'replacements' list")
        requests = [(str(row["slot"]), Path(str(row["wav"]))) for row in rows]
        return _run(lambda: audo_patch.plan(Path(source), requests, dict(catalogue.document)))

    @staticmethod
    def _ranges(items: Sequence[Mapping[str, Any]]) -> tuple[DeclaredRange, ...]:
        return tuple(
            DeclaredRange(int(item["iso_offset"]), int(item["video_bytes"]), f"audo:{item['slot_id']}")
            for item in items
        )

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        prepared = self._prepared(Path(source), recipe, catalogue)
        items = [{key: value for key, value in item.items() if not key.startswith("_")}
                 for item in prepared["items"]]
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(str(item["slot_id"]) for item in items),
            declared_ranges=self._ranges(items),
            document={"items": items,
                      "payload_bytes": sum(int(item["video_bytes"]) for item in items)},
        )

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        source, destination = Path(source), Path(destination)
        _guard_destination(source, destination)
        prepared = self._prepared(source, recipe, catalogue)
        report = _run(lambda: audo_patch.apply(prepared, source, destination, work_dir=work_dir))
        return Receipt(
            schema=report["schema"],
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=self._ranges(report["replacements"]),
            document=report,
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = audo_verify.verify(Path(source), Path(destination), dict(receipt.document),
                                        wav_dir=None, run_iso_verifier=True)
        except TOOL_ERRORS as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        passed = str(report.get("verdict", "")).upper() == "PASS"
        iso_check = report.get("iso9660_verifier") or {}
        if iso_check.get("ran") and not iso_check.get("passed"):
            passed = False
        return Verdict(
            passed,
            f"audio verifier: {report.get('verdict', '?')} · {report.get('declared_slots', 0)} slot(s) checked · "
            f"{report.get('changed_bytes', 0):,} bytes changed, "
            f"{report.get('changed_outside_declared_spans', 0)} outside the declared spans · "
            f"tree identical: {report.get('tree_identical')}.",
            report,
        )

    # -- the audio protocol --------------------------------------------

    def decode_wav(self, source: Path, target: Target) -> bytes:
        """The slot's current sound off the user's own disc, as 16-bit PCM WAV bytes."""

        slot = target.raw
        image = iso_lib.open_image(str(source))
        packs = inventory_lib.discover_packs(image)
        archive = inventory_lib.VirtualPacks(str(source), packs)
        archive.open()
        try:
            payload = _run(lambda: archive.read(int(slot["payload_virtual_offset"]),
                                                int(slot["video_bytes"])))
        finally:
            archive.close()
        per_channel = int(slot["per_channel_bytes"])
        channels = int(slot["channels"])
        planes = []
        for index in range(channels):
            samples, _p1, _p2 = _run(lambda block=payload[index * per_channel:(index + 1) * per_channel]:
                                     spu_adpcm.decode(block))
            planes.append(samples)
        frames = min(len(plane) for plane in planes) if planes else 0
        return _wav_bytes(planes, frames, int(slot["sample_rate"]))

    # -- what CI proves it on ------------------------------------------

    #: 40 SPU blocks of silence: a slot big enough to hold a short replacement.
    SYNTHETIC_BLOCKS = 40
    SYNTHETIC_RATE = 11025

    def synthetic_source(self, work_dir: Path) -> Path:
        payload = spu_adpcm.encode([0] * (spu_adpcm.BLOCK_FRAMES * self.SYNTHETIC_BLOCKS))
        image = colour_catalog.build_synthetic_iso(entries=[
            ("BEEP.BIN", audo_catalog.build_audo_chunk("beep", 1, self.SYNTHETIC_RATE, payload)),
            ("18H0.IFF", colour_catalog.unif_chunk(0xFFA29895, 0xFF272320)),
        ])
        path = Path(work_dir) / "nfl2k5-ps2-audio-synthetic.iso"
        path.write_bytes(image)
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        if not catalogue.targets:
            raise Refusal("the synthetic disc carries no sound slot; rebuild the fixture")
        target = catalogue.targets[0]
        slot = target.raw
        # The harness gives a lane one room and hands it back only the
        # catalogue, so the WAV a conformance edit names is written beside the
        # synthetic source the catalogue was built from.
        rate = int(slot["sample_rate"])
        frames = max(1, min(int(slot["max_frames"]), rate // 4))
        planes = [[int(round(9000 * math.sin(2 * math.pi * 440 * index / rate)))
                   for index in range(frames)]
                  for _channel in range(int(slot["channels"]))]
        path = Path(catalogue.source).resolve().parent / f"conformance-{slot['slot_id'].replace(':', '-')}.wav"
        path.write_bytes(_wav_bytes(planes, frames, rate))
        return (Edit(target.key, {"wav": str(path)}, note="conformance"),)


def _wav_bytes(planes: Sequence[Sequence[int]], frames: int, rate: int) -> bytes:
    """A canonical 16-bit PCM RIFF/WAVE file: ``fmt `` and ``data``, nothing else."""

    channels = max(1, len(planes))
    interleaved: list[int] = []
    for index in range(frames):
        for plane in planes:
            interleaved.append(int(plane[index]))
    pcm = struct.pack("<%dh" % len(interleaved), *interleaved)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 2, channels * 2, 16)
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


# --------------------------------------------------------------------------
# Disc inventory: the read-only lane
# --------------------------------------------------------------------------

class DiscInventoryLane:
    """Every named resource on the user's disc, listed and never written.

    There is no PS2 disc texture writer and no GS codec in this product, so the
    inventory is the honest shape for the whole texture surface: it says what
    is there -- name, kind, pixel format, dimensions, stored size -- and offers
    no edit at all.  ``read_only`` is the marker a shell reads to draw the page
    as a table instead of an editor, and ``plan``, ``build`` and ``verify``
    refuse rather than quietly doing nothing.
    """

    lane_id = "textures.disc_inventory"
    capability_id = "nfl2k5ps2.textures.disc_inventory"
    surface = "textures"
    title = "Everything on the disc"
    classification = "read-only-mapped"
    recipe_schema = inventory_lib.SCHEMA
    validators = (
        "tools/validate_nfl2k5_ps2_disc_inventory.sh",
        "tools/validate_nfl2k5_ps2_disc_inventory.bat",
    )
    fixed_allocation = False
    #: The marker the shell reads.  A protocol with no member of its own would
    #: match every lane at runtime, so this value is the whole distinction.
    read_only = True

    REFUSAL = ("The disc inventory only lists what is on your disc; it writes nothing, so there is "
               "nothing here to plan, build or verify. Use the colour, text, roster, playbook, "
               "stadium or audio lane to change something.")

    #: A retail disc walks 550,000 rows; a page of a few thousand is a table,
    #: more is a data dump.  The document keeps every census either way.
    MAX_TARGETS = 5000

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        rows: list[dict[str, Any]] = []

        def sink(row: dict) -> None:
            if len(rows) < self.MAX_TARGETS:
                rows.append(row)

        def tick(message: object) -> None:
            if progress is not None:
                progress(str(message))

        report, _side = _run(lambda: inventory_lib.inventory(
            str(source), jobs=1, progress=tick if progress else None, row_sink=sink))
        targets = []
        for index, row in enumerate(rows):
            name = str(row.get("name") or "")
            fourcc = str(row.get("fourcc") or "")
            geometry = row.get("geometry") or {}
            size = row.get("size")
            detail = [piece for piece in (
                fourcc,
                f"{geometry.get('width')}×{geometry.get('height')}" if geometry.get("width") else "",
                str(row.get("format") or ""),
                f"{int(size):,} bytes" if isinstance(size, int) else "",
            ) if piece]
            targets.append(Target(
                key=f"{index}:{row.get('entry_index', 0)}:{name or fourcc or 'unnamed'}",
                label=name or f"{fourcc or 'resource'} {index}",
                detail=" · ".join(detail),
                budget="Read-only: this lane never writes to your disc.",
                searchable=f"{name} {fourcc} {row.get('format', '')}",
                raw=row,
                fields=(
                    Field("name", "note", "Name", "The resource's own name on the disc.",
                          read_only=True),
                    Field("format", "note", "Format", "The pixel format the disc stores it in.",
                          read_only=True),
                    Field("dimensions", "note", "Dimensions", "Width by height, in pixels.",
                          read_only=True),
                    Field("size", "note", "Stored size", "How many bytes the resource occupies.",
                          read_only=True),
                ),
            ))
        document = dict(report)
        document["schema"] = inventory_lib.SCHEMA
        document["rows_listed"] = len(targets)
        return Catalogue(
            schema=inventory_lib.SCHEMA,
            lane_id=self.lane_id,
            source=str(source),
            targets=tuple(targets),
            document=document,
        )

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        """An empty recipe.  Composing is not where a read-only lane refuses.

        A refusal here would be a refusal while the user is still looking at
        the list, which is the wrong moment and the wrong sentence.  The three
        methods that would *write* are where this lane says no.
        """

        return {"schema": self.recipe_schema, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    def synthetic_source(self, work_dir: Path) -> Path:
        image, _expected = inventory_lib._build_synthetic_disc()
        path = Path(work_dir) / "nfl2k5-ps2-inventory-synthetic.iso"
        path.write_bytes(image)
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


# --------------------------------------------------------------------------
# The synthetic playbook disc
# --------------------------------------------------------------------------

def _synthetic_playbook_iso() -> bytes:
    """A SLUS-20919-shaped image holding two structurally valid ``PLAY`` books.

    The playbook tools have no fixture builder of their own -- the shipped
    tests build one from the play codec's own constants -- so the smallest
    honest thing this lane can do is build the same body here, field by field,
    out of the codec and inspector the *writer* uses.  Nothing is copied from a
    disc: every byte below is computed from the format's own rules.
    """

    from mod_editor.core import nfl2k5_formation_play_writer as fpwriter
    from mod_editor.core import nfl2k5_play_codec as codec
    from mod_editor.core import nfl2k5_playbook_inspector as inspector

    # Family 1 (defense), type code 4: the retail validator's ball-handler and
    # snapper rules are unconditional there, so a two-node coverage chain in
    # every slot is the smallest play it accepts.
    play_flags = 4 | (1 << 6)
    chain_ops = (0x1B, 0x0D)
    formations, plays, categories = 3, 2, 2

    def put_rel(body: bytearray, field: int, destination: int) -> None:
        """The book's self-relative pointer form: ``destination = field - 1 + value``."""

        struct.pack_into("<i", body, field, destination - field + 1)

    def build_body() -> bytes:
        body = bytearray(inspector.BODY_SIZE)
        body[0x0C:0x10] = b"PLAY"
        struct.pack_into("<I", body, 0x10, 0x11)
        struct.pack_into("<i", body, 0x14, -19)
        body[0x20:0x28] = b"p\0l\0b\0\0\0"

        pool = bytearray()
        offset: dict[str, int] = {}
        for key, text in (("book", "TESTBOOK"), ("formation", "FORMATION"),
                          ("play", "PLAY"), ("category", "CATEGORY")):
            offset[key] = inspector.STRING_BASE + len(pool)
            pool += text.encode("utf-16le") + b"\0\0"
        body[inspector.STRING_BASE:inspector.STRING_BASE + len(pool)] = pool
        struct.pack_into("<I", body, fpwriter.POOL_COUNT_WORD, len(pool) // 2)

        blob = bytearray()
        for _slot in range(codec.SLOT_COUNT):
            nodes = [codec.Node(op, 0, codec.decode_operands(op, 0)) for op in chain_ops]
            codec.assign_node_flags(nodes)
            for node in nodes:
                blob += node.to_bytes()
        body[inspector.NODE_BASE:inspector.NODE_BASE + len(blob)] = blob

        struct.pack_into("<I", body, 0x34, formations)
        struct.pack_into("<I", body, 0x38, plays)
        struct.pack_into("<I", body, 0x3C, categories)
        struct.pack_into("<I", body, 0x40, len(blob) // inspector.NODE_SIZE)
        put_rel(body, 0x30, offset["book"])
        put_rel(body, 0x44, inspector.FORMATION_BASE)
        put_rel(body, 0x48, inspector.FORMATION_AUX_BASE)
        put_rel(body, 0x60, inspector.PLAY_BASE)
        put_rel(body, 0x64, inspector.CATEGORY_BASE)
        put_rel(body, 0x68, inspector.NODE_BASE)

        chains = []
        for slot in range(codec.SLOT_COUNT):
            start = inspector.NODE_BASE + slot * len(chain_ops) * inspector.NODE_SIZE
            chains.append([bytes(body[start + index * inspector.NODE_SIZE:
                                      start + (index + 1) * inspector.NODE_SIZE])
                           for index in range(len(chain_ops))])
        staged = [(0, chains[slot]) for slot in range(codec.SLOT_COUNT)]
        descriptors = [codec.build_descriptor(play_flags, staged, slot, 0xB0)
                       for slot in range(codec.SLOT_COUNT)]

        for index in range(plays):
            base = inspector.PLAY_BASE + index * inspector.PLAY_SIZE
            put_rel(body, base, offset["play"])
            struct.pack_into("<I", body, base + 4, play_flags)
            for slot in range(codec.SLOT_COUNT):
                struct.pack_into("<I", body, base + 8 + slot * 8, descriptors[slot])
                put_rel(body, base + 0x0C + slot * 8,
                        inspector.NODE_BASE + slot * len(chain_ops) * inspector.NODE_SIZE)

        for index in range(formations):
            base = inspector.FORMATION_BASE + index * inspector.FORMATION_SIZE
            put_rel(body, base, offset["formation"])
            struct.pack_into("<I", body, base + 4,
                             codec.FORMATION_FLAG_UNDER_CENTER | (1 << 8))
            body[base + 0x0D:base + 0x18] = bytes(range(11))
            for slot in range(codec.SLOT_COUNT):
                record = base + codec.FORMATION_SLOT_BASE + slot * codec.FORMATION_SLOT_STRIDE
                body[record + 1] = (codec.NO_MIRROR << 4) | 3
                lateral = (slot - 5) * 120
                struct.pack_into("<hhh", body, record + 2, lateral, lateral, lateral)
                struct.pack_into("<hhh", body, record + 8, 0, 0, 0)
            aux = inspector.FORMATION_AUX_BASE + index * inspector.FORMATION_AUX_SIZE
            for link in range(inspector.FORMATION_PLAY_LINKS):
                struct.pack_into("<H", body, aux + link * 2, 0 if link == 0 else 0x01FF)

        for index in range(categories):
            base = inspector.CATEGORY_BASE + index * inspector.CATEGORY_SIZE
            put_rel(body, base, offset["category"])
            body[base + 4] = index
            body[base + 5:base + 16] = bytes(range(11))
        return bytes(body)

    def resource(body: bytes) -> bytes:
        head = bytearray(playbook_patch.RESOURCE_HEADER_SIZE)
        head[0:4] = b"PLAY"
        struct.pack_into("<4I", head, 4, len(body), len(body), 0, 0)
        return bytes(head) + body

    body = build_body()
    resources = [(0x49CD9F21, resource(body)), (0x2C3DEF14, resource(body))]
    count = len(resources)
    table_end = playbook_patch.OUTER_HEADER_SIZE + count * playbook_patch.OUTER_ENTRY_SIZE
    block = -(-table_end // playbook_patch.ALIGNMENT)
    placed = []
    for name_id, payload in resources:
        placed.append((name_id, len(payload), block, payload))
        block += -(-len(payload) // playbook_patch.ALIGNMENT)
    pack = bytearray(block * playbook_patch.ALIGNMENT)
    struct.pack_into("<III", pack, 0, count, 0, 1)
    struct.pack_into("<I", pack, 0x0C, block)
    for index, (name_id, size, at, payload) in enumerate(placed):
        struct.pack_into("<III", pack,
                         playbook_patch.OUTER_HEADER_SIZE + index * playbook_patch.OUTER_ENTRY_SIZE,
                         name_id, size, at)
        pack[at * playbook_patch.ALIGNMENT:at * playbook_patch.ALIGNMENT + len(payload)] = payload
    return iso_lib.build_synthetic_iso(
        files=[(b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\nVER = 1.01\r\nVMODE = NTSC\r\n"),
               (b"SLUS_209.19;1", b"\x7fELF" + bytes(4092))],
        sub_name=b"VC_20919",
        sub_files=[(b"0.;1", bytes(pack))])


#: The six lanes this module adds, in the order the studio's pages run.
DISC_LANES: tuple[Any, ...] = (
    RosterLane(),
    TextLane(),
    StadiumLane(),
    AudioLane(),
    PlaybooksLane(),
    DiscInventoryLane(),
)

__all__ = [
    "AudioLane",
    "DISC_LANES",
    "DiscInventoryLane",
    "FACE_SHIELDS",
    "MAX_CUSTOM_NAME_CHARS",
    "PlaybooksLane",
    "RosterLane",
    "StadiumLane",
    "TextLane",
    "binary32",
]
