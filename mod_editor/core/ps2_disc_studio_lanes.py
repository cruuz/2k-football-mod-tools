"""The six PlayStation 2 on-disc writers as one Qt-free surface for the PS2 Disc Studio.

Each ``Lane`` here wraps one Phase 2 lane -- text banks, playbooks, uniform
colours, the disc roster, stadium position lanes, exact-slot AUDO sounds --
and does four things the window and the build worker both need:

* **list targets** from the catalogue the lane's own catalogue tool built from
  the user's disc (never from the committed ``reports/`` JSON, which is
  evidence, not release data);
* **check an edit before it is staged**, quoting the budget and naming the fix
  (the inline refusal a tab shows under its editor);
* **compose a recipe** in the exact schema the lane's patcher accepts, then
  **plan** it (the patcher's own dry run) so every refusal the patcher would
  make surfaces before any image exists;
* **apply** by calling the lane's own ``patch``/``apply`` to write a NEW image,
  and **verify** with the lane's independent verifier.

Nothing here reshapes a lane tool.  The tools are imported lazily by name from
``tools/`` -- the same directory the disc inventory and save windows put on
``sys.path`` -- and every refusal a tool raises is surfaced verbatim as a
:class:`LaneRefusal`, never re-worded: the export window's rule that one
condition has one sentence.

Reading the user's disc for display is allowed and used (a string's current
text, a uniform's current colour words, a historic roster's players, a book's
formation names, a scene's vertex positions), but none of it is written to the
sidecar cache, a recipe preview, a receipt or a report; recipes carry the
user's values and selectors only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import functools
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .errors import ValidationError

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

SERIAL = "SLUS-20919"

#: Fixed queue order.  Independent of the tab order a user clicks through.
LANE_ORDER = ("text", "playbooks", "colors", "roster", "stadium", "audio")


class Ps2DiscStudioError(ValidationError):
    """Anything the studio refuses: an input, a plan, a destination, a tool."""


class LaneRefusal(Ps2DiscStudioError):
    """A lane's own refusal, carried verbatim with the lane that made it."""

    def __init__(self, lane_id: str, message: str, stage: str = "") -> None:
        super().__init__(message)
        self.lane_id = lane_id
        self.stage = stage


def _tool(name: str):
    """Import one shipped tool by module name, naming it when it is absent."""
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise Ps2DiscStudioError(
            f"The tool {name}.py is not available in this build: {exc}"
        ) from exc


def tool_path(name: str) -> Path:
    """The file a lane's catalogue tool is run from (as a subprocess)."""
    path = TOOLS / f"{name}.py"
    if not path.is_file():
        raise Ps2DiscStudioError(f"The tool {path.name} is not available in this build.")
    return path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(document: object) -> bytes:
    """Bytes, not text: no platform newline question, LF everywhere."""
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _load_json(path: Path, what: str) -> dict:
    try:
        document = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise Ps2DiscStudioError(f"{what} could not be read: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise Ps2DiscStudioError(f"{what} is not a JSON object: {path}")
    return document


def _read_at(path: Path, offset: int, size: int) -> bytes:
    """Positional read with seek+read (no os.pread: Windows has none)."""
    with open(path, "rb") as handle:
        handle.seek(offset)
        data = handle.read(size)
    if len(data) != size:
        raise Ps2DiscStudioError(
            f"{Path(path).name} ended inside a read at offset {offset}; the image is truncated."
        )
    return data


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


# --------------------------------------------------------------------------
# Shared value types
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Target:
    """One catalogue row as a tab lists it.  ``data`` is the tool's own row."""

    key: str
    label: str
    detail: str
    budget: str
    search: str
    editable: bool = True
    reason: str = ""
    group: str = ""
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class StagedEdit:
    """One edit the user added to a lane's recipe."""

    lane_id: str
    target_key: str
    values: dict
    summary: str


@dataclass(frozen=True)
class RecipeStep:
    """One patcher run: a recipe in the lane's schema plus a note for the queue."""

    lane_id: str
    recipe: dict
    note: str
    edits: int


@dataclass(frozen=True)
class PlanResult:
    """A lane's dry run: what would change, in the patcher's own terms."""

    lane_id: str
    edits: int
    summary: str
    detail: dict


@dataclass(frozen=True)
class Verdict:
    """What the lane's independent verifier said about one written image."""

    lane_id: str
    passed: bool
    summary: str
    report: dict


@dataclass(frozen=True)
class CatalogueScope:
    """How much of the disc a catalogue build covers (the stadium lane has two)."""

    id: str
    label: str
    note: str


DEFAULT_SCOPE = CatalogueScope("default", "The whole lane", "")


class Lane:
    """Common surface; one subclass per writer below."""

    id: str = ""
    title: str = ""
    registry_id: str = ""
    catalogue_tool: str = ""
    patch_tool: str = ""
    verify_tool: str = ""
    recipe_schema: str = ""
    #: Plain-words caveats a tab shows.  Distilled from the registry row.
    caveats: Tuple[str, ...] = ()
    #: What the user should expect a build step of this lane to cost.
    time_note: str = ""
    #: A tab's one-line description of what may change.
    summary: str = ""

    # -- catalogue ----------------------------------------------------

    def scopes(self) -> Tuple[CatalogueScope, ...]:
        return (DEFAULT_SCOPE,)

    def catalogue_command(self, python: str, iso: Path, output: Path,
                          scope: str = DEFAULT_SCOPE.id) -> List[str]:
        raise NotImplementedError

    def load_catalogue(self, path: Path) -> dict:
        raise NotImplementedError

    def catalogue_summary(self, catalogue: dict) -> str:
        raise NotImplementedError

    def targets(self, catalogue: dict) -> List[Target]:
        raise NotImplementedError

    # -- editing ------------------------------------------------------

    def check_edit(self, target: Target, values: dict,
                   staged: Sequence[StagedEdit] = ()) -> Optional[str]:
        """The inline refusal for ``values`` on ``target``, or ``None``."""
        raise NotImplementedError

    def edit_summary(self, target: Target, values: dict) -> str:
        raise NotImplementedError

    def compose_recipes(self, catalogue: dict, edits: Sequence[StagedEdit],
                        context: "RecipeContext") -> List[RecipeStep]:
        raise NotImplementedError

    # -- the patcher and the verifier ---------------------------------

    def plan(self, source: Path, recipe: dict, catalogue_path: Path,
             work_dir: Path) -> PlanResult:
        raise NotImplementedError

    def apply(self, source: Path, destination: Path, recipe: dict,
              catalogue_path: Path, work_dir: Path) -> dict:
        raise NotImplementedError

    def verify(self, source: Path, destination: Path, receipt: dict,
               recipe: dict, catalogue_path: Path, work_dir: Path) -> Verdict:
        raise NotImplementedError

    def receipt_summary(self, receipt: dict) -> str:
        return "written"

    # -- helpers shared by the subclasses -----------------------------

    def _refuse(self, message: str, stage: str = "") -> LaneRefusal:
        return LaneRefusal(self.id, str(message).strip() or "the lane refused without a reason", stage)

    def _run(self, stage: str, call: Callable[[], Any]) -> Any:
        """Call into a lane tool; surface its refusal verbatim, tagged with the lane."""
        try:
            return call()
        except LaneRefusal:
            raise
        except Ps2DiscStudioError as exc:
            raise self._refuse(str(exc), stage) from exc
        except (ValueError, AssertionError, OSError, KeyError, TypeError,
                struct.error, ValidationError) as exc:
            raise self._refuse(str(exc) or exc.__class__.__name__, stage) from exc

    @staticmethod
    def _target_by_key(targets: Sequence[Target], key: str) -> Target:
        for target in targets:
            if target.key == key:
                return target
        raise Ps2DiscStudioError(f"{key} is not in this disc's catalogue.")


@dataclass(frozen=True)
class RecipeContext:
    """What composing a recipe may need beyond the edits themselves."""

    source: Path
    catalogue_path: Path
    catalogue_sha256: str = ""


# --------------------------------------------------------------------------
# Text banks
# --------------------------------------------------------------------------

class TextLane(Lane):
    id = "text"
    title = "Text"
    registry_id = "nfl2k5ps2.menus.text_banks"
    catalogue_tool = "nfl2k5_ps2_text_target_catalog"
    patch_tool = "nfl2k5_ps2_text_patch"
    verify_tool = "nfl2k5_ps2_text_verify"
    recipe_schema = "nfl2k5_ps2_text_patch/v1"
    summary = ("Rewrite display text inside the five fixed-allocation text banks. "
               "A replacement may be shorter or the same length as the original, never longer.")
    caveats = (
        "Bytes proven, nothing on a screen yet: no edited label has been seen drawn, "
        "and a menu that lays out from a measured string width could re-flow when a label shortens.",
        "The budget is the original string's own length: this disc's pools have no spare bytes anywhere.",
        "281 allocations are shared by more than one record; editing one changes every record that uses it "
        "(the picker says 'used by N records').",
        "Inline tokens such as |CROSS| draw glyphs and must stay in place; 215 strings are read-only "
        "because their consumer is lookup, not display.",
    )
    time_note = ("A text build copies the whole image and rewrites the 1 GiB pack that holds the bank: "
                 "minutes, for a handful of bytes.")

    def catalogue_command(self, python, iso, output, scope=DEFAULT_SCOPE.id):
        return [python, str(tool_path(self.catalogue_tool)), "--iso", str(iso), "--output", str(output)]

    def load_catalogue(self, path):
        document = _load_json(path, "The text catalogue")
        tool = _tool(self.catalogue_tool)
        if document.get("schema") != tool.SCHEMA:
            raise Ps2DiscStudioError(f"{path.name} is not a {tool.SCHEMA} catalogue.")
        if not isinstance(document.get("strings"), list) or not isinstance(document.get("banks"), list):
            raise Ps2DiscStudioError(f"{path.name} carries no string rows.")
        return document

    def catalogue_summary(self, catalogue):
        summary = catalogue.get("summary", {})
        return (f"{summary.get('bank_count', 0)} banks · {summary.get('string_count', 0):,} strings · "
                f"{summary.get('editable_count', 0):,} editable, {summary.get('read_only_count', 0):,} read-only")

    @staticmethod
    def limit_of(row: dict) -> int:
        return max(0, int(row["allocation_bytes"]) // 2 - 1)

    def targets(self, catalogue):
        reasons = catalogue.get("scope", {}).get("reason_codes", {})
        rows: List[Target] = []
        for row in catalogue["strings"]:
            limit = self.limit_of(row)
            used = int(row.get("used_code_units", 0))
            references = int(row.get("reference_count", 1))
            tokens = list(row.get("tokens") or [])
            detail = [row.get("bank_kind", ""), f"{used} of {limit} code units"]
            if references > 1:
                detail.append(f"used by {references} records")
            if tokens:
                detail.append("keeps " + " ".join(tokens))
            reason = "" if row.get("editable") else reasons.get(row.get("reason_code", ""), row.get("reason_code", ""))
            rows.append(Target(
                key=row["selector"], label=row.get("label", row["selector"]),
                detail=" · ".join(piece for piece in detail if piece),
                budget=f"Up to {limit} characters (the original's own length)",
                search=" ".join([row.get("label", ""), row["selector"], row.get("bank_kind", "")]).lower(),
                editable=bool(row.get("editable")), reason=reason,
                group=row["selector"].split(":", 1)[0], data=row,
            ))
        return rows

    def check_edit(self, target, values, staged=()):
        text = values.get("new_text")
        if not target.editable:
            return f"This string is read-only: {target.reason} Choose one of the editable strings."
        if not isinstance(text, str) or text == "":
            return "Type the replacement text; an empty string cannot be written."
        if "\x00" in text:
            return "The replacement may not contain a NUL character; remove it."
        limit = self.limit_of(target.data)
        units = len(text.encode("utf-16le")) // 2
        if units > limit:
            over = units - limit
            return (f"{units} characters is {over} over the budget of {limit}. The budget is the "
                    f"original string's own length; shorten the replacement to {limit}.")
        tool = _tool(self.catalogue_tool)
        original_tokens = list(target.data.get("tokens") or [])
        new_tokens = tool.tokens_in(text)
        if new_tokens != original_tokens:
            if original_tokens:
                return ("Keep the inline tokens exactly as the original has them, in order: "
                        + " ".join(original_tokens) + ". The engine draws a glyph where each one sits.")
            return ("The replacement adds an inline token (" + " ".join(new_tokens)
                    + ") the original does not have; remove it.")
        if _sha256(text.encode("utf-16le")) == target.data.get("text_sha256"):
            return "That is the text already there; change it or leave the string alone."
        for other in staged:
            if other.lane_id == self.id and other.target_key == target.key:
                return "This string is already in the recipe; remove that edit first to change it."
        return None

    def edit_summary(self, target, values):
        return f"{target.label} → {values.get('new_text', '')!r}"

    def compose_recipes(self, catalogue, edits, context):
        by_selector = {row["selector"]: row for row in catalogue["strings"]}
        recipe_edits = []
        for edit in edits:
            row = by_selector.get(edit.target_key)
            if row is None:
                raise self._refuse(f"{edit.target_key} is not in this disc's catalogue.", "compose")
            recipe_edits.append({
                "selector": edit.target_key,
                "new_text": edit.values["new_text"],
                "expect_sha256": row["text_sha256"],
            })
        if not recipe_edits:
            return []
        return [RecipeStep(self.id, {"edits": recipe_edits},
                           f"{_plural(len(recipe_edits), 'string')}", len(recipe_edits))]

    def plan(self, source, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        report = self._run("plan", lambda: patcher.patch(
            source_iso=str(source), destination_iso=None, edits=recipe["edits"], dry_run=True))
        changed = report["recipe"]["changed_byte_count"]
        return PlanResult(self.id, len(report["edits"]),
                          f"{_plural(len(report['edits']), 'string')} · {changed:,} bytes would change "
                          f"inside {_plural(len(report['packs']), 'pack')}", report)

    def apply(self, source, destination, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        return self._run("write", lambda: patcher.patch(
            source_iso=str(source), destination_iso=str(destination), edits=recipe["edits"]))

    def verify(self, source, destination, receipt, recipe, catalogue_path, work_dir):
        verifier = _tool(self.verify_tool)
        report = self._run("verify", lambda: verifier.verify(
            source_iso=str(source), destination_iso=str(destination), recipe=recipe,
            patch_report=receipt, iso_write_report=receipt.get("iso_write_report")))
        passed = str(report.get("verdict", "")).lower() == "pass"
        return Verdict(self.id, passed,
                       f"text verifier: {report.get('verdict', '?')} · {len(report.get('edits', []))} edits located · "
                       f"{report.get('changed_byte_count', 0):,} bytes differ, exactly the edited allocations",
                       report)

    def receipt_summary(self, receipt):
        return (f"{_plural(len(receipt.get('edits', [])), 'string')} · "
                f"{receipt.get('recipe', {}).get('changed_byte_count', 0):,} bytes changed")

    # -- reading the user's disc for display ----------------------------

    def read_display_texts(self, iso_path: Path, catalogue: dict) -> Dict[str, str]:
        """Current text per selector, decoded from the user's own disc.

        Shown in the picker only.  It is never cached, never put in a recipe
        or a receipt; the catalogue deliberately carries digests instead.
        """
        tool = _tool(self.catalogue_tool)
        by_bank: Dict[str, List[dict]] = {}
        for row in catalogue["strings"]:
            by_bank.setdefault(row["selector"].split(":", 1)[0], []).append(row)
        texts: Dict[str, str] = {}
        for bank in catalogue["banks"]:
            if not bank.get("decoded") or bank["bank_id"] not in by_bank:
                continue
            try:
                body = _read_at(Path(iso_path), int(bank["iso_byte_offset"]), int(bank["stored_size"]))
            except Ps2DiscStudioError:
                continue
            if bank.get("body_sha256") and _sha256(body) != bank["body_sha256"]:
                continue        # the disc is not the one the catalogue describes
            try:
                pool = self._pool(tool, bank["kind"], body)
            except Exception:   # a bank this disc no longer decodes: show nothing
                continue
            by_start = {item.start: item.text for item in pool}
            for row in by_bank[bank["bank_id"]]:
                text = by_start.get(int(row["body_offset"]))
                if text is not None:
                    texts[row["selector"]] = text
        return texts

    @staticmethod
    def _pool(tool, kind: str, body: bytes):
        if kind == "STRG":
            return tool.parse_strg(body)["pool"]
        if kind == "SITU":
            return tool.parse_situ(body)["pool"]
        if kind == "CRED":
            return tool.parse_pointer_pool(
                body, "CRED", descriptor_offset=tool.CRED_DESCRIPTOR,
                record_count=tool.CRED_RECORD_COUNT, record_size=tool.CRED_RECORD_SIZE,
                pointer_fields=tool.CRED_POINTER_FIELDS, numeric_fields=tool.CRED_NUMERIC_FIELDS)["pool"]
        if kind == "TRIV":
            return tool.parse_pointer_pool(
                body, "TRIV", descriptor_offset=tool.TRIV_DESCRIPTOR,
                record_count=tool.TRIV_RECORD_COUNT, record_size=tool.TRIV_RECORD_SIZE,
                pointer_fields=tool.TRIV_POINTER_FIELDS, numeric_fields=tool.TRIV_NUMERIC_FIELDS)["pool"]
        raise Ps2DiscStudioError(f"unsupported text bank kind {kind}")


# --------------------------------------------------------------------------
# Uniform colours
# --------------------------------------------------------------------------

def describe_selector(selector: Optional[str]) -> str:
    """``18H0`` -> ``package 18 · home · variant 0``; anything else is shown as is."""
    if not selector or len(selector) < 4 or not selector[:2].isdigit() or selector[2] not in "HA":
        return selector or "unnamed package"
    side = "home" if selector[2] == "H" else "away"
    return f"package {selector[:2]} · {side} · variant {selector[3:]}"


@functools.lru_cache(maxsize=1)
def _xbox_uniform_names() -> Dict[str, str]:
    """Team names per selector from the Xbox uniform catalogue, when this machine has one.

    The Xbox side derives them from the user's own XISO; a PS2-only machine has
    no such file, and the colours tab then names packages by selector alone.
    """
    try:
        from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
        catalog = load_nfl2k5_uniform_catalog()
    except Exception:
        return {}
    names: Dict[str, str] = {}
    for uniform_set in getattr(catalog, "uniform_sets", ()):
        selector = str(getattr(uniform_set, "selector", "") or "").upper()
        teams = tuple(getattr(uniform_set, "team_names", ()) or ())
        style = str(getattr(uniform_set, "style_display", "") or "")
        label = ", ".join(str(team) for team in teams)
        if style:
            label = f"{label} — {style}" if label else style
        if selector and label:
            names[selector] = label
    return names


class ColorsLane(Lane):
    id = "colors"
    title = "Colours"
    registry_id = "nfl2k5ps2.colors.unif_words"
    catalogue_tool = "nfl2k5_ps2_unif_color_target_catalog"
    patch_tool = "nfl2k5_ps2_unif_color_patch"
    verify_tool = "nfl2k5_ps2_unif_color_verify"
    recipe_schema = "nfl2k5_ps2_unif_color_recipe/v1"
    WORDS = ("facemask", "turtleneck")
    summary = ("Rewrite the facemask and turtleneck packed-colour words of any of the 634 uniform "
               "packages. Each edit changes at most eight bytes.")
    caveats = (
        "Bytes proven, pixels not: no PCSX2 capture has confirmed which material each word tints on this platform.",
        "Which word tints what is inherited from the Xbox executable trace, not re-derived for the PS2 disc.",
        "A package that already holds the colours you choose is refused as a no-op, not written silently.",
        "Team names appear only when this machine also has the Xbox uniform catalogue; otherwise packages "
        "are named by selector (package number, home or away, variant).",
    )
    time_note = ("A colour build copies the whole image and rewrites the 1 GiB pack holding the package: "
                 "minutes for eight bytes. Packages in both packs are built as two steps.")

    def catalogue_command(self, python, iso, output, scope=DEFAULT_SCOPE.id):
        return [python, str(tool_path(self.catalogue_tool)), "--iso", str(iso), "--output", str(output)]

    def load_catalogue(self, path):
        document = _load_json(path, "The colour catalogue")
        tool = _tool(self.catalogue_tool)
        if document.get("schema") != tool.SCHEMA:
            raise Ps2DiscStudioError(f"{path.name} is not a {tool.SCHEMA} catalogue.")
        if not isinstance(document.get("targets"), list):
            raise Ps2DiscStudioError(f"{path.name} carries no uniform targets.")
        return document

    def catalogue_summary(self, catalogue):
        summary = catalogue.get("summary", {})
        return (f"{summary.get('targets', 0)} uniform packages · {summary.get('home_packages', 0)} home, "
                f"{summary.get('away_packages', 0)} away · {summary.get('rejected', 0)} unsafe")

    def targets(self, catalogue):
        names = _xbox_uniform_names()
        rows: List[Target] = []
        for row in catalogue["targets"]:
            selector = row.get("selector") or f"outer:{row['outer_index']}"
            decoded = describe_selector(row.get("selector"))
            team = names.get(str(selector).upper(), "")
            label = f"{selector} — {team}" if team else f"{selector} — {decoded}"
            unsafe = ""
            if row.get("compressed"):
                unsafe = "its Unif body is LZ-compressed; this lane refuses to recompress"
            elif not row.get("matches_xbox_offsets"):
                unsafe = "its descriptor does not resolve the colour pair to the proved offset"
            rows.append(Target(
                key=str(selector), label=label,
                detail=f"{row.get('iso_path', '')} · outer entry {row.get('outer_index')}",
                budget="Two packed ARGB words of exactly 4 bytes each (#RRGGBB or AARRGGBB)",
                search=" ".join([str(selector), decoded, team, str(row.get("outer_index"))]).lower(),
                editable=not unsafe, reason=unsafe, group=row.get("iso_path", ""), data=row,
            ))
        for row in catalogue.get("rejected", []):
            selector = row.get("selector") or f"outer:{row['outer_index']}"
            rows.append(Target(
                key=str(selector), label=f"{selector} — {describe_selector(row.get('selector'))}",
                detail=f"outer entry {row.get('outer_index')}", budget="",
                search=str(selector).lower(), editable=False,
                reason=str(row.get("reason", "unsafe target")), data=row,
            ))
        return rows

    def check_edit(self, target, values, staged=()):
        if not target.editable:
            return f"This package cannot be written: {target.reason}. Choose another package."
        tool = _tool(self.catalogue_tool)
        chosen = 0
        current = values.get("_current")   # (facemask, turtleneck) words read from the disc, if known
        same = 0
        for index, name in enumerate(self.WORDS):
            value = values.get(name)
            if value in (None, ""):
                continue
            try:
                word = tool.parse_color(value)
            except Exception as exc:
                return f"{name}: {exc}. A packed colour word is exactly 4 bytes; use #RRGGBB or AARRGGBB."
            chosen += 1
            if isinstance(current, (list, tuple)) and len(current) == 2 and current[index] == word:
                same += 1
        if not chosen:
            return "Choose a facemask colour, a turtleneck colour, or both."
        if same == chosen:
            return "The package already holds those colours; pick a different colour or leave it alone."
        for other in staged:
            if other.lane_id == self.id and other.target_key == target.key:
                return "This package is already in the recipe; remove that edit first to change it."
        return None

    def edit_summary(self, target, values):
        parts = [f"{name} {values[name]}" for name in self.WORDS if values.get(name) not in (None, "")]
        return f"{target.key}: " + ", ".join(parts)

    def compose_recipes(self, catalogue, edits, context):
        by_key = {(row.get("selector") or f"outer:{row['outer_index']}"): row for row in catalogue["targets"]}
        grouped: Dict[str, List[dict]] = {}
        for edit in edits:
            row = by_key.get(edit.target_key)
            if row is None:
                raise self._refuse(f"{edit.target_key} is not in this disc's catalogue.", "compose")
            entry = {"selector": edit.target_key}
            for name in self.WORDS:
                if edit.values.get(name) not in (None, ""):
                    entry[name] = str(edit.values[name]).strip()
            grouped.setdefault(str(row.get("iso_path", "")), []).append(entry)
        steps = []
        for iso_path in sorted(grouped):
            recipe = {"schema": self.recipe_schema, "edits": grouped[iso_path]}
            steps.append(RecipeStep(self.id, recipe,
                                    f"{_plural(len(grouped[iso_path]), 'package')} in {iso_path}",
                                    len(grouped[iso_path])))
        return steps

    def _parsed(self, patcher, recipe):
        return self._run("recipe", lambda: patcher.parse_recipe(recipe))

    def plan(self, source, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        pinned = self.load_catalogue(catalogue_path)
        parsed = self._parsed(patcher, recipe)
        prepared = self._run("plan", lambda: patcher.plan(Path(source), parsed, pinned))
        edits = prepared["edits"]
        detail = {"edits": [{k: v for k, v in item.items() if k != "replacement"} for item in edits],
                  "files": sorted(prepared["by_file"])}
        return PlanResult(self.id, len(edits),
                          f"{_plural(len(edits), 'package')} · {len(edits) * patcher.SPAN_BYTES} bytes "
                          f"would change in {', '.join(sorted(prepared['by_file']))}", detail)

    def apply(self, source, destination, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        pinned = self.load_catalogue(catalogue_path)
        parsed = self._parsed(patcher, recipe)
        return self._run("write", lambda: patcher.apply(
            Path(source), Path(destination), parsed, pinned_catalog=pinned, work_dir=work_dir))

    def verify(self, source, destination, receipt, recipe, catalogue_path, work_dir):
        verifier = _tool(self.verify_tool)
        report = self._run("verify", lambda: verifier.verify(Path(source), Path(destination), receipt))
        passed = str(report.get("result", "")).upper() == "PASS"
        return Verdict(self.id, passed,
                       f"colour verifier: {report.get('result', '?')} · {report.get('edits_checked', 0)} edits checked · "
                       f"{report.get('unif_records_decoded', 0)} Unif records decoded · "
                       f"{report.get('unchanged_bytes_compared', 0):,} unchanged bytes compared", report)

    def receipt_summary(self, receipt):
        return f"{_plural(len(receipt.get('edits', [])), 'package')} · {len(receipt.get('edits', [])) * 8} bytes changed"

    def read_current_words(self, iso_path: Path, catalogue: dict) -> Dict[str, Tuple[int, int]]:
        """Each package's current (facemask, turtleneck) words, read from the user's disc for swatches."""
        words: Dict[str, Tuple[int, int]] = {}
        path = Path(iso_path)
        with open(path, "rb") as handle:
            for row in catalogue["targets"]:
                key = row.get("selector") or f"outer:{row['outer_index']}"
                handle.seek(int(row["colour_offset_in_iso"]))
                span = handle.read(8)
                if len(span) != 8 or _sha256(span) != row.get("retail_span_sha256"):
                    continue
                words[str(key)] = tuple(struct.unpack("<II", span))  # type: ignore[assignment]
        return words


# --------------------------------------------------------------------------
# Disc roster
# --------------------------------------------------------------------------

FACE_SHIELD_LABELS = {0: "None", 1: "Clear", 2: "Dark"}


class RosterLane(Lane):
    id = "roster"
    title = "Roster"
    registry_id = "nfl2k5ps2.players.disc_roster"
    catalogue_tool = "nfl2k5_ps2_disc_roster_target_catalog"
    patch_tool = "nfl2k5_ps2_disc_roster_patch"
    verify_tool = "nfl2k5_ps2_disc_roster_verify"
    recipe_schema = "nfl2k5_ps2_disc_roster_recipe/v1"
    NAME_FIELDS = ("first_name", "last_name")
    summary = ("Change first and last names, jersey numbers and face shields in the boot roster "
               "and the 75 historic rosters. Names must fit the bytes the original occupies.")
    caveats = (
        "Bytes proven, pixels not: no edited player has been seen in game.",
        "A loaded roster or franchise save may override this disc seed; witness from a fresh franchise "
        "with no roster save loaded.",
        "A name's budget is its own stored span, terminator included; 897 of 5,094 name slots are empty "
        "placeholders and cannot take a name.",
        "Team membership, ratings, position and face id are not writes here.",
    )
    time_note = ("A roster build copies the whole image and rewrites the 1 GiB pack holding the arena: "
                 "minutes for a few bytes. Each roster you edit is its own step.")

    def catalogue_command(self, python, iso, output, scope=DEFAULT_SCOPE.id):
        return [python, str(tool_path(self.catalogue_tool)), "--iso", str(iso), "--output", str(output)]

    def load_catalogue(self, path):
        document = _load_json(path, "The roster catalogue")
        tool = _tool(self.catalogue_tool)
        if document.get("schema") != tool.SCHEMA:
            raise Ps2DiscStudioError(f"{path.name} is not a {tool.SCHEMA} catalogue.")
        if not isinstance(document.get("rosters"), list) or not isinstance(document.get("players"), list):
            raise Ps2DiscStudioError(f"{path.name} carries no roster rows.")
        return document

    def catalogue_summary(self, catalogue):
        summary = catalogue.get("summary", {})
        return (f"{summary.get('rost_chunks', 0)} rosters ({summary.get('historic_rosters', 0)} historic) · "
                f"boot roster: {summary.get('boot_players', 0):,} players, "
                f"{summary.get('writable_name_slots', 0):,} writable name slots")

    @staticmethod
    def roster_key(roster: dict) -> str:
        return "boot" if roster.get("boot_roster") else f"outer:{roster['outer_index']}"

    def rosters(self, catalogue: dict) -> List[dict]:
        """The roster choices a tab offers, boot first."""
        rows = [row for row in catalogue["rosters"]]
        rows.sort(key=lambda row: (0 if row.get("boot_roster") else 1, int(row["outer_index"])))
        return rows

    @staticmethod
    def _name_limit(player: dict, field_name: str) -> int:
        return max(0, (int(player.get(field_name + "_capacity", 0)) - 2) // 2)

    def player_targets(self, roster_key: str, players: Sequence[dict]) -> List[Target]:
        rows: List[Target] = []
        for player in players:
            first, last = player.get("first_name") or "", player.get("last_name") or ""
            key = f"{roster_key}:{player['pool']}:{player['index']}"
            budgets = []
            for field_name in self.NAME_FIELDS:
                if player.get(field_name + "_writable"):
                    budgets.append(f"{field_name.replace('_', ' ')} up to {self._name_limit(player, field_name)} characters")
                else:
                    budgets.append(f"{field_name.replace('_', ' ')} not writable")
            label = f"{first} {last}".strip() or "(empty slot)"
            rows.append(Target(
                key=key, label=f"{label} #{player.get('jersey_number', '?')}",
                detail=f"{player['pool'].replace('_', ' ')} {player['index']}",
                budget="; ".join(budgets) + "; jersey 0–99; face shield None/Clear/Dark",
                search=" ".join([first, last, str(player.get("jersey_number", "")), str(player["index"]),
                                 player["pool"]]).lower(),
                editable=True, group=roster_key, data=dict(player, roster_key=roster_key),
            ))
        return rows

    def targets(self, catalogue):
        return self.player_targets("boot", catalogue.get("players", []))

    def check_edit(self, target, values, staged=()):
        player = target.data
        changes = 0
        for field_name in self.NAME_FIELDS:
            value = values.get(field_name)
            if value in (None, ""):
                continue
            if not isinstance(value, str):
                return f"{field_name.replace('_', ' ')} must be text."
            if "\x00" in value:
                return f"{field_name.replace('_', ' ')} may not contain a NUL character; remove it."
            if not player.get(field_name + "_writable"):
                references = int(player.get(field_name + "_references", 0))
                if int(player.get(field_name + "_capacity", 0)) <= 2:
                    return (f"This player's {field_name.replace('_', ' ')} slot is an empty placeholder with "
                            "no room for a name; choose a player whose name is already stored.")
                return (f"This player's {field_name.replace('_', ' ')} string is shared by {references} records, "
                        "so rewriting it would change another record too; choose a player with an unshared name.")
            limit = self._name_limit(player, field_name)
            units = len(value.encode("utf-16le")) // 2
            if units > limit:
                return (f"{field_name.replace('_', ' ')}: {units} characters is {units - limit} over the "
                        f"budget of {limit}; the name must fit the bytes the original occupies. Shorten it to {limit}.")
            if value == (player.get(field_name) or ""):
                return f"That is the {field_name.replace('_', ' ')} already there; change it or leave the field blank."
            changes += 1
        jersey = values.get("jersey_number")
        if jersey not in (None, ""):
            if not isinstance(jersey, int) or isinstance(jersey, bool) or not 0 <= jersey <= 99:
                return "Jersey number must be a whole number from 0 to 99."
            if jersey == player.get("jersey_number"):
                return f"The jersey is already {jersey}; choose another number or leave it blank."
            changes += 1
        shield = values.get("face_shield")
        if shield not in (None, ""):
            if shield not in (0, 1, 2):
                return "Face shield must be None, Clear or Dark; the reserved fourth value is refused."
            changes += 1
        if not changes:
            return "Change at least one of first name, last name, jersey number or face shield."
        for other in staged:
            if other.lane_id == self.id and other.target_key == target.key:
                return "This player is already in the recipe; remove that edit first to change it."
        return None

    def edit_summary(self, target, values):
        parts = []
        for field_name in self.NAME_FIELDS:
            if values.get(field_name) not in (None, ""):
                parts.append(f"{field_name.replace('_', ' ')} → {values[field_name]!r}")
        if values.get("jersey_number") not in (None, ""):
            parts.append(f"jersey → {values['jersey_number']}")
        if values.get("face_shield") not in (None, ""):
            parts.append(f"face shield → {FACE_SHIELD_LABELS.get(values['face_shield'], values['face_shield'])}")
        return f"{target.label}: " + ", ".join(parts)

    def compose_recipes(self, catalogue, edits, context):
        grouped: Dict[str, List[dict]] = {}
        for edit in edits:
            roster_key, pool, index = edit.target_key.rsplit(":", 2)
            entry: Dict[str, Any] = {"pool": pool, "player": int(index)}
            for field_name in self.NAME_FIELDS:
                if edit.values.get(field_name) not in (None, ""):
                    entry[field_name] = edit.values[field_name]
            for field_name in ("jersey_number", "face_shield"):
                if edit.values.get(field_name) not in (None, ""):
                    entry[field_name] = int(edit.values[field_name])
            grouped.setdefault(roster_key, []).append(entry)
        steps = []
        for roster_key in sorted(grouped, key=lambda key: (key != "boot", key)):
            recipe = {"schema": self.recipe_schema, "roster": roster_key, "edits": grouped[roster_key]}
            steps.append(RecipeStep(self.id, recipe,
                                    f"{_plural(len(grouped[roster_key]), 'player')} in the "
                                    f"{'boot roster' if roster_key == 'boot' else 'historic roster ' + roster_key}",
                                    len(grouped[roster_key])))
        return steps

    def plan(self, source, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        pinned = self.load_catalogue(catalogue_path)
        parsed = self._run("recipe", lambda: patcher.parse_recipe(recipe))
        prepared = self._run("plan", lambda: patcher.plan(Path(source), parsed, pinned))
        edits = prepared["edits"]
        changed = sum(int(item["span_size"]) for item in edits)
        detail = {"roster": prepared["roster"],
                  "edits": [{k: v for k, v in item.items() if k != "replacement"} for item in edits]}
        return PlanResult(self.id, len(edits),
                          f"{_plural(len(edits), 'field span')} · {changed:,} bytes would change in "
                          f"{prepared['roster']['iso_path']} (outer entry {prepared['roster']['outer_index']})",
                          detail)

    def apply(self, source, destination, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        pinned = self.load_catalogue(catalogue_path)
        parsed = self._run("recipe", lambda: patcher.parse_recipe(recipe))
        return self._run("write", lambda: patcher.apply(
            Path(source), Path(destination), parsed, pinned_catalog=pinned, work_dir=work_dir))

    def verify(self, source, destination, receipt, recipe, catalogue_path, work_dir):
        verifier = _tool(self.verify_tool)
        report = self._run("verify", lambda: verifier.verify(Path(source), Path(destination), receipt))
        passed = str(report.get("result", "")).upper() == "PASS"
        tables = report.get("target_tables", {})
        return Verdict(self.id, passed,
                       f"roster verifier: {report.get('result', '?')} · {report.get('edits_checked', 0)} edits checked · "
                       f"{report.get('rost_resources_decoded', 0)} ROST resources decoded · "
                       f"{len(tables)} table counts unchanged · "
                       f"{report.get('unchanged_bytes_compared', 0):,} unchanged bytes compared", report)

    def receipt_summary(self, receipt):
        edits = receipt.get("edits", [])
        return f"{_plural(len(edits), 'field span')} · {sum(int(e.get('span_size', 0)) for e in edits):,} bytes changed"

    def decode_players(self, iso_path: Path, catalogue: dict, roster_key: str) -> List[dict]:
        """The players of one roster, decoded from the user's disc (historic rosters are not catalogued)."""
        if roster_key == "boot":
            return list(catalogue.get("players", []))
        tool = _tool(self.catalogue_tool)
        index = int(roster_key.split(":", 1)[1], 0)
        matches = [row for row in catalogue["rosters"] if int(row["outer_index"]) == index]
        if not matches:
            raise Ps2DiscStudioError(f"{roster_key} is not a catalogued roster on this disc.")
        roster = matches[0]
        if roster.get("compressed"):
            raise Ps2DiscStudioError(
                f"Roster {roster_key} is LZ-compressed; this lane refuses it rather than recompressing.")
        body = _read_at(Path(iso_path), int(roster["body_offset_in_iso"]), int(roster["stored_size"]))
        if _sha256(body) != roster.get("body_sha256"):
            raise Ps2DiscStudioError(f"Roster {roster_key} on the disc no longer matches the catalogue.")
        decoded = self._run("decode", lambda: tool.decode_roster(body, roster_key))
        return self._run("decode", lambda: tool.decode_players(body, decoded["tables"]))


# --------------------------------------------------------------------------
# Playbooks
# --------------------------------------------------------------------------

MAX_CUSTOM_NAME_CHARS = 40


def clean_custom_name(value: object) -> Optional[str]:
    """The Xbox writer's rule for a custom name, restated for the inline check."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise Ps2DiscStudioError("A custom name must be text.")
    name = value.strip()
    if not 1 <= len(name) <= MAX_CUSTOM_NAME_CHARS:
        raise Ps2DiscStudioError(f"A custom name must be 1 through {MAX_CUSTOM_NAME_CHARS} characters.")
    if any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in name):
        raise Ps2DiscStudioError("A custom name may use printable ASCII only.")
    return name


class PlaybooksLane(Lane):
    id = "playbooks"
    title = "Playbooks"
    registry_id = "nfl2k5ps2.scripts.director_playbook"
    catalogue_tool = "nfl2k5_ps2_playbook_target_catalog"
    patch_tool = "nfl2k5_ps2_playbook_patch"
    verify_tool = "nfl2k5_ps2_playbook_verify"
    recipe_schema = "nfl2k5_ps2_playbook_patch/v1"
    summary = ("Create formations and plays inside the 37 fixed-capacity playbooks by cloning a donor "
               "and placing it in an empty slot; the Xbox writer does the work unchanged.")
    caveats = (
        "Bytes proven, nothing on a screen yet: no authored formation has been seen line up, on either platform.",
        "Capacities are enforced, not negotiated: 50 formations, 270 plays and 3,500 nodes per book; "
        "eight books are already at the play cap and take replacements only.",
        "Plays created by the in-game editor may live in a memory-card save that overlays the disc book "
        "at load and masks a disc edit; that is untested on PS2.",
        "A created formation or play is a clone of a donor plus your positions and chains; menu group "
        "bits reuse a value the book already uses.",
    )
    time_note = ("A playbook build copies the whole image and rewrites the 1 GiB pack holding the book: "
                 "minutes for a few hundred bytes. Each book is compiled and re-validated before the copy starts.")

    def catalogue_command(self, python, iso, output, scope=DEFAULT_SCOPE.id):
        return [python, str(tool_path(self.catalogue_tool)), "--iso", str(iso), "--output", str(output)]

    def load_catalogue(self, path):
        document = _load_json(path, "The playbook catalogue")
        tool = _tool(self.catalogue_tool)
        if document.get("schema") != tool.SCHEMA:
            raise Ps2DiscStudioError(f"{path.name} is not a {tool.SCHEMA} catalogue.")
        if not isinstance(document.get("books"), list):
            raise Ps2DiscStudioError(f"{path.name} carries no books.")
        return document

    def catalogue_summary(self, catalogue):
        totals = catalogue.get("totals", {})
        return (f"{totals.get('books', 0)} books · {totals.get('formations', 0):,} formations, "
                f"{totals.get('plays', 0):,} plays · headroom {totals.get('formation_headroom', 0)} formations, "
                f"{totals.get('play_headroom', 0)} plays · {totals.get('books_at_play_capacity', 0)} books at the play cap")

    def targets(self, catalogue):
        rows: List[Target] = []
        for book in catalogue["books"]:
            cap = " · AT THE PLAY CAP" if book.get("at_play_capacity") else ""
            rows.append(Target(
                key=str(book["book_id"]), label=str(book.get("book_name", book["book_id"])),
                detail=(f"{book.get('formations', 0)}/50 formations · {book.get('plays', 0)}/270 plays · "
                        f"{book.get('nodes', 0):,} nodes{cap}"),
                budget=(f"Room for {book.get('formation_headroom', 0)} more formations, "
                        f"{book.get('play_headroom', 0)} more plays and {book.get('node_headroom', 0):,} more nodes; "
                        f"names up to {MAX_CUSTOM_NAME_CHARS} printable ASCII characters"),
                search=" ".join([str(book.get("book_name", "")), str(book["book_id"])]).lower(),
                editable=True, data=book,
            ))
        return rows

    def check_edit(self, target, values, staged=()):
        formations = list(values.get("formations") or [])
        plays = list(values.get("plays") or [])
        links = list(values.get("links") or [])
        if not (formations or plays or links):
            return "Add a formation, a play or a link before staging this book."
        book = target.data
        adding_plays = sum(1 for row in plays if row.get("replace_index") is None)
        adding_formations = sum(1 for row in formations if row.get("replace_index") is None)
        if adding_plays and adding_plays > int(book.get("play_headroom", 0)):
            return (f"This book holds {book.get('plays', 0)} of 270 plays and can take "
                    f"{book.get('play_headroom', 0)} more; adding {adding_plays} is refused. "
                    "Replace an existing play instead, or choose a book with room.")
        if adding_formations and adding_formations > int(book.get("formation_headroom", 0)):
            return (f"This book holds {book.get('formations', 0)} of 50 formations and can take "
                    f"{book.get('formation_headroom', 0)} more; adding {adding_formations} is refused.")
        for row in formations:
            try:
                clean_custom_name(row.get("custom_name"))
            except Ps2DiscStudioError as exc:
                return f"Formation name: {exc}"
            slots = row.get("slot_positions")
            if slots is not None and (not isinstance(slots, (list, tuple)) or len(slots) != 11
                                      or any(not isinstance(pair, (list, tuple)) or len(pair) != 2 for pair in slots)):
                return "A formation needs exactly 11 [x, depth] slot positions in centimetres."
            if not isinstance(row.get("donor_formation_index", 0), int):
                return "The donor formation must be chosen from the book."
        for row in plays:
            try:
                clean_custom_name(row.get("custom_name"))
            except Ps2DiscStudioError as exc:
                return f"Play name: {exc}"
            if not isinstance(row.get("donor_play_index", 0), int):
                return "The donor play must be chosen from the book."
        for row in links:
            if not isinstance(row.get("formation_index"), int) or not isinstance(row.get("play_index"), int):
                return "A link needs a formation index and a play index."
        for other in staged:
            if other.lane_id == self.id and other.target_key == target.key:
                return "This book is already in the recipe; remove that edit first to change it."
        return None

    def edit_summary(self, target, values):
        counts = [(len(values.get("formations") or []), "formation"),
                  (len(values.get("plays") or []), "play"),
                  (len(values.get("links") or []), "link")]
        return f"{target.label}: " + ", ".join(_plural(n, w) for n, w in counts if n)

    def compose_recipes(self, catalogue, edits, context):
        recipe_edits = []
        for edit in edits:
            entry: Dict[str, Any] = {"book_id": edit.target_key}
            for key in ("formations", "plays", "links"):
                if edit.values.get(key):
                    entry[key] = list(edit.values[key])
            recipe_edits.append(entry)
        if not recipe_edits:
            return []
        return [RecipeStep(self.id, {"schema": self.recipe_schema, "edits": recipe_edits},
                           f"{_plural(len(recipe_edits), 'book')}", len(recipe_edits))]

    def _parsed(self, patcher, recipe, work_dir):
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        path = Path(work_dir) / "playbook-recipe.json"
        path.write_bytes(_json_bytes(recipe))
        return self._run("recipe", lambda: patcher.load_recipe(path))

    def plan(self, source, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        parsed = self._parsed(patcher, recipe, work_dir)
        compiled = self._run("plan", lambda: patcher.compile_edits(Path(source), parsed))
        rows = []
        for item in compiled:
            rows.append({"book_id": item["target"].id_text, "before": item["before"], "after": item["after"],
                         "changed_byte_count": item["changed_byte_count"],
                         "changed_ranges": len(item["changed_ranges"])})
        changed = sum(row["changed_byte_count"] for row in rows)
        packs = {item["target"].pack.letter for item in compiled}
        if len(packs) > 1:
            raise self._refuse(f"this tool patches one pack per run; the recipe spans {len(packs)}", "plan")
        return PlanResult(self.id, len(rows),
                          f"{_plural(len(rows), 'book')} compiled · {changed:,} bytes would change · "
                          + "; ".join(f"{row['book_id']}: {row['before']['formations']}f/{row['before']['plays']}p → "
                                      f"{row['after']['formations']}f/{row['after']['plays']}p" for row in rows),
                          {"books": rows})

    def apply(self, source, destination, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        parsed = self._parsed(patcher, recipe, work_dir)
        return self._run("write", lambda: patcher.patch(Path(source), parsed, Path(destination), workdir=work_dir))

    def verify(self, source, destination, receipt, recipe, catalogue_path, work_dir):
        verifier = _tool(self.verify_tool)
        report = self._run("verify", lambda: verifier.verify(Path(source), Path(destination), receipt))
        passed = str(report.get("verdict", "")).upper() == "PASS"
        return Verdict(self.id, passed,
                       f"playbook verifier: {report.get('verdict', '?')} · {report.get('declared_edits', 0)} books checked · "
                       f"{report.get('changed_byte_total', 0):,} bytes changed in "
                       f"{len(report.get('changed_ranges', []))} ranges · "
                       f"{report.get('play_resources_found', 0)} books found", report)

    def receipt_summary(self, receipt):
        edits = receipt.get("play_edits", [])
        return (f"{_plural(len(edits), 'book')} · "
                f"{sum(int(e.get('changed_byte_count', 0)) for e in edits):,} bytes changed")

    def read_book(self, iso_path: Path, book_key: str):
        """``(Nfl2k5Playbook, body)`` of one book, from the user's disc, for the designers."""
        patcher = _tool(self.patch_tool)
        from mod_editor.core import nfl2k5_playbook_inspector as inspector
        wanted = int(str(book_key), 16) & 0xFFFFFFFF
        targets = self._run("read", lambda: patcher.find_targets(Path(iso_path)))
        for target in targets:
            if target.book_id == wanted:
                raw = self._run("read", lambda: patcher.read_resource(Path(iso_path), target))
                body = raw[patcher.RESOURCE_HEADER_SIZE:]
                book = self._run("read", lambda: inspector._parse_body(
                    body, asset_id=target.id_text, outer_index=target.entry_index))
                return book, body
        raise Ps2DiscStudioError(f"Book {book_key} is not on this disc.")


# --------------------------------------------------------------------------
# Stadium position lanes
# --------------------------------------------------------------------------

def binary32(value: float) -> float:
    """The nearest binary32 to ``value``; the patcher refuses anything else."""
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


class StadiumLane(Lane):
    id = "stadium"
    title = "Stadium"
    registry_id = "nfl2k5ps2.stadiums.position_lanes"
    catalogue_tool = "nfl2k5_ps2_stadium_target_catalog"
    patch_tool = "nfl2k5_ps2_stadium_position_patch"
    verify_tool = "nfl2k5_ps2_stadium_position_verify"
    recipe_schema = "nfl2k5_ps2_stadium_position_recipe/v1"
    PROVED_ENTRY = "1556:2"
    summary = ("Move every vertex of a catalogued stadium position lane by an offset. Vertex count and "
               "topology stay identical; the scene is recompressed back into the exact span it owns.")
    caveats = (
        "Bytes proven, pixels not: nothing has been booted, and which lane is which piece of stadium is not established.",
        "Whether the recompressed scene fits its fixed span is only decided during the build, and the retail packer "
        "left 0 to 16 spare bytes per scene; a refusal there leaves no image behind.",
        "One stadium edit is a tens-of-minutes build: the optimal-parse refit and its fill step dominate.",
        "Several targets can share one position span (aliases); the writer refuses a recipe that edits two of them, "
        "and the picker shows how many share each span.",
    )
    time_note = ("Expect tens of minutes per stadium step (the real-disc trial took 17 minutes to refit one scene) "
                 "on top of the image copy. Cancel is honoured; a refused fit writes nothing.")

    def scopes(self):
        return (
            CatalogueScope("proved", "The proved scene only (entry 1556, chunk 2)",
                           "About a minute: decodes one scene and lists its 1,041 lanes."),
            CatalogueScope("all", "Every stadium scene on the disc",
                           "Long: walks all 4,322 entries and decodes every stadium-named scene. "
                           "The catalogue tool has not been run to completion on the retail disc before."),
        )

    def catalogue_command(self, python, iso, output, scope="proved"):
        command = [python, str(tool_path(self.catalogue_tool)), "--iso", str(iso), "--json", str(output)]
        if scope == "all":
            command.append("--scan")
        else:
            command.extend(["--entry", self.PROVED_ENTRY])
        return command

    def load_catalogue(self, path):
        patcher = _tool(self.patch_tool)
        document = self._run("catalogue", lambda: patcher.load_catalog(str(path)))
        return document["value"]

    def catalogue_summary(self, catalogue):
        summary = catalogue.get("summary", {})
        return (f"{summary.get('scenes', 0)} scenes · {summary.get('shapes', 0)} shapes · "
                f"{summary.get('target_count', 0):,} position lanes over "
                f"{summary.get('distinct_position_spans', 0):,} distinct spans · "
                f"{summary.get('vertex_total', 0):,} vertices")

    def targets(self, catalogue):
        rows: List[Target] = []
        scenes = catalogue.get("scenes", [])
        for row in catalogue["targets"]:
            shape = row.get("shape", {})
            position = row.get("position", {})
            count = int(position.get("vertex_count", 0))
            shared = int(row.get("payload_span_target_count", 1))
            scene = scenes[row["scene_index"]]["identity"] if row.get("scene_index", 0) < len(scenes) else {}
            detail = [f"{count} vertices", f"batch {row.get('batch', {}).get('index')}",
                      f"entry {scene.get('entry_index')} chunk {scene.get('chunk_index')}"]
            if shared > 1:
                detail.append(f"span shared by {shared} targets")
            rows.append(Target(
                key=row["target_id"], label=f"{shape.get('name') or 'shape'} {shape.get('index')} · lane {position.get('lane_ordinal_within_batch', 0)}",
                detail=" · ".join(detail),
                budget=f"Exactly {count} vertices; x, y, z offsets are added to every one and rounded to binary32",
                search=" ".join([row["target_id"], str(shape.get("name", "")), str(count)]).lower(),
                editable=True, group=str(row.get("scene_index", 0)), data=row,
            ))
        return rows

    @staticmethod
    def _span_key(row: dict) -> Tuple[int, int, int]:
        payload = row["position"]["payload"]
        return (int(row.get("scene_index", 0)), int(payload["offset"]), int(payload["size"]))

    def check_edit(self, target, values, staged=()):
        offsets = []
        for axis in ("dx", "dy", "dz"):
            value = values.get(axis, 0.0)
            try:
                number = float(value)
            except (TypeError, ValueError):
                return f"{axis} must be a number."
            if not math.isfinite(number):
                return f"{axis} must be a finite number."
            offsets.append(number)
        if all(offset == 0.0 for offset in offsets):
            return "Enter an x, y or z offset other than zero; moving nothing is refused as a no-op."
        for other in staged:
            if other.lane_id != self.id:
                continue
            if other.target_key == target.key:
                return "This lane is already in the recipe; remove that edit first to change it."
            other_row = other.values.get("_row")
            if isinstance(other_row, dict) and self._span_key(other_row) == self._span_key(target.data):
                return (f"This lane shares its position span with {other.target_key}, which is already in the "
                        "recipe; one span can be edited once.")
        return None

    def edit_summary(self, target, values):
        return (f"{target.label}: move {target.data['position']['vertex_count']} vertices by "
                f"({values.get('dx', 0)}, {values.get('dy', 0)}, {values.get('dz', 0)})")

    def compose_recipes(self, catalogue, edits, context):
        if not edits:
            return []
        if not context.catalogue_sha256:
            raise self._refuse("the stadium recipe must pin the catalogue file's digest", "compose")
        tool = _tool(self.catalogue_tool)
        by_id = {row["target_id"]: row for row in catalogue["targets"]}
        by_scene: Dict[int, List[StagedEdit]] = {}
        for edit in edits:
            row = by_id.get(edit.target_key)
            if row is None:
                raise self._refuse(f"{edit.target_key} is not in this disc's catalogue.", "compose")
            by_scene.setdefault(int(row.get("scene_index", 0)), []).append(edit)
        steps = []
        for scene_index in sorted(by_scene):
            decoded = self.decode_scene(context.source, catalogue, scene_index)
            recipe_edits = []
            vertices = 0
            for edit in by_scene[scene_index]:
                row = by_id[edit.target_key]
                dx, dy, dz = (float(edit.values.get(axis, 0.0)) for axis in ("dx", "dy", "dz"))
                positions = []
                for x, y, z in self.positions_of(decoded, row):
                    positions.append([binary32(x + dx), binary32(y + dy), binary32(z + dz)])
                vertices += len(positions)
                recipe_edits.append({"target_id": edit.target_key, "positions": positions})
            recipe = {"schema": self.recipe_schema,
                      "catalog": {"schema": tool.SCHEMA, "sha256": context.catalogue_sha256},
                      "edits": recipe_edits}
            steps.append(RecipeStep(self.id, recipe,
                                    f"{_plural(len(recipe_edits), 'lane')} · {vertices:,} vertices in scene {scene_index}",
                                    len(recipe_edits)))
        return steps

    def _recipe_path(self, recipe, work_dir) -> Path:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        path = Path(work_dir) / "stadium-recipe.json"
        path.write_bytes(_json_bytes(recipe))
        return path

    def plan(self, source, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        catalog = self._run("catalogue", lambda: patcher.load_catalog(str(catalogue_path)))
        recipe_path = self._recipe_path(recipe, work_dir)
        loaded = self._run("recipe", lambda: patcher.load_recipe(str(recipe_path), catalog))
        scene_index = int(loaded["edits"][0]["row"]["scene_index"]) if loaded["edits"] else 0
        decoded = self.decode_scene(source, catalog["value"], scene_index)
        edited, written = self._run("plan", lambda: patcher.apply_positions(decoded, loaded["edits"]))
        changed = sum(1 for a, b in zip(decoded, edited) if a != b)
        vertices = sum(int(item["vertex_count"]) for item in written)
        return PlanResult(self.id, len(written),
                          f"{_plural(len(written), 'lane')} · {vertices:,} vertices · {changed:,} decoded bytes would "
                          "change · whether the recompressed scene fits its fixed span is decided during the build",
                          {"edits": [{"target_id": item["target_id"], "vertex_count": item["vertex_count"],
                                      "written_bytes": sum(hi - lo for lo, hi in item["ranges"])} for item in written]})

    def apply(self, source, destination, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        recipe_path = self._recipe_path(recipe, work_dir)
        return self._run("write", lambda: patcher.patch(
            str(source), str(catalogue_path), str(recipe_path), str(destination)))

    def verify(self, source, destination, receipt, recipe, catalogue_path, work_dir):
        verifier = _tool(self.verify_tool)
        recipe_path = self._recipe_path(recipe, work_dir)
        report = self._run("verify", lambda: verifier.verify(
            str(source), str(destination), str(catalogue_path), str(recipe_path)))
        passed = str(report.get("verdict", "")).lower() == "pass"
        decoded = report.get("decoded", {})
        return Verdict(self.id, passed,
                       f"stadium verifier: {report.get('verdict', '?')} · {decoded.get('changed_bytes', 0):,} decoded bytes "
                       f"changed in {decoded.get('changed_ranges', 0)} ranges, every one inside a declared lane · "
                       f"wrapper identical: {report.get('chunk', {}).get('wrapper_identical')}", report)

    def receipt_summary(self, receipt):
        compression = receipt.get("compression", {})
        return (f"{_plural(len(receipt.get('edits', [])), 'lane')} · "
                f"{receipt.get('decoded_diff', {}).get('changed_bytes', 0):,} decoded bytes changed · "
                f"refit {compression.get('mode', '?')}, {compression.get('rebuilt_consumed_bytes', 0):,} of "
                f"{compression.get('stored_size', 0):,} stored bytes")

    def decode_scene(self, iso_path: Path, catalogue: dict, scene_index: int) -> bytes:
        """The decoded SCNE (system + video) the recipe's positions are read from; never persisted."""
        patcher = _tool(self.patch_tool)
        inventory = _tool("nfl2k5_ps2_disc_inventory")
        txtr = _tool("nfl_txtr")
        iso_lib = _tool("ps2_iso9660")
        scenes = catalogue.get("scenes", [])
        if not 0 <= scene_index < len(scenes):
            raise Ps2DiscStudioError(f"Scene {scene_index} is not in this catalogue.")
        identity = scenes[scene_index]["identity"]

        def read() -> bytes:
            image = iso_lib.open_image(str(iso_path))
            packs = patcher._pack_paths(image)
            archive = inventory.VirtualPacks(str(iso_path), [(letter, base, size)
                                                             for _path, base, size, letter in packs])
            archive.open()
            try:
                _outer, table = inventory.read_outer_table(archive)
                chunk = patcher._locate_chunk(archive, table, identity)
                return archive.read(chunk["virtual_offset"], chunk["span_size"])
            finally:
                archive.close()

        span = self._run("decode", read)
        decoded, _info = self._run("decode", lambda: txtr.decode_chunk(
            span, txtr.parse_chunks(span, allow_trailing=True)[0]))
        if _sha256(decoded[:int(identity["system_bytes"])]) != identity["system_sha256"]:
            raise self._refuse("the scene's system buffer differs from the catalogued one; rebuild the catalogue "
                               "for this disc", "decode")
        return decoded

    @staticmethod
    def positions_of(decoded: bytes, row: dict) -> List[Tuple[float, float, float]]:
        payload = row["position"]["payload"]
        count = int(row["position"]["vertex_count"])
        start = int(payload["offset"])
        return [struct.unpack_from("<3f", decoded, start + index * 16) for index in range(count)]


# --------------------------------------------------------------------------
# AUDO sounds
# --------------------------------------------------------------------------

class AudioLane(Lane):
    id = "audio"
    title = "Audio"
    registry_id = "nfl2k5ps2.audio.audo_exact_slot_replace"
    catalogue_tool = "nfl2k5_ps2_audo_target_catalog"
    patch_tool = "nfl2k5_ps2_audo_patch"
    verify_tool = "nfl2k5_ps2_audo_verify"
    recipe_schema = "nfl2k5_ps2_audo_recipe/v1"
    summary = ("Replace any of the 844 standalone AUDO sounds from a 16-bit PCM WAV, encoded to SPU-ADPCM "
               "and fitted to the slot's exact byte count.")
    caveats = (
        "Bytes proven, nothing heard yet: no replaced sound has been through an emulator's speaker.",
        "690 of 844 slots share a name with another slot, so replacing one may change an unexpected or "
        "duplicate-sounding cue; only the 154 disc-unique names can be attributed at all.",
        "A slot never grows: a longer sound is refused with the slot's exact capacity, and a shorter one "
        "is followed by silent filler the SPU never plays.",
        "The WAV must be strict 16-bit PCM with only the fmt and data chunks and the slot's own channel count; "
        "another sample rate is resampled to the slot's.",
    )
    time_note = ("An audio build copies the whole image and rewrites the 1 GiB pack holding the slot: "
                 "minutes per sound (the real-disc trial measured about 167 s to write and 34 s to verify).")

    def catalogue_command(self, python, iso, output, scope=DEFAULT_SCOPE.id):
        return [python, str(tool_path(self.catalogue_tool)), "--iso", str(iso), "--report", str(output), "--quiet"]

    def load_catalogue(self, path):
        document = _load_json(path, "The audio catalogue")
        tool = _tool(self.catalogue_tool)
        if document.get("schema") != tool.SCHEMA:
            raise Ps2DiscStudioError(f"{path.name} is not a {tool.SCHEMA} catalogue.")
        if not isinstance(document.get("slots"), list):
            raise Ps2DiscStudioError(f"{path.name} carries no slots.")
        return document

    def catalogue_summary(self, catalogue):
        totals = catalogue.get("totals", {})
        return (f"{totals.get('slots', 0)} sound slots · {totals.get('mono', 0)} mono, {totals.get('stereo', 0)} stereo · "
                f"{totals.get('unique_names', 0)} disc-unique names")

    @staticmethod
    def capacity_seconds(slot: dict) -> float:
        rate = int(slot.get("sample_rate", 0)) or 1
        return int(slot.get("max_frames", 0)) / rate

    def targets(self, catalogue):
        rows: List[Target] = []
        for slot in catalogue["slots"]:
            seconds = self.capacity_seconds(slot)
            channels = "stereo" if int(slot.get("channels", 1)) == 2 else "mono"
            shared = "" if slot.get("unique_name") else " · shared name"
            rows.append(Target(
                key=slot["slot_id"], label=f"{slot.get('name', slot['slot_id'])}",
                detail=f"{channels} · {slot.get('sample_rate')} Hz · up to {seconds:.2f} s{shared}",
                budget=(f"Up to {seconds:.2f} s ({slot.get('max_frames'):,} frames at {slot.get('sample_rate')} Hz), "
                        f"{channels} 16-bit PCM WAV"),
                search=" ".join([str(slot.get("name", "")), slot["slot_id"], channels,
                                 str(slot.get("sample_rate"))]).lower(),
                editable=True, group=str(slot.get("pack", "")), data=slot,
            ))
        return rows

    def describe_wav(self, target: Target, wav_path: Path) -> dict:
        """Frames, seconds and fit for a WAV against a slot; raises the patcher's own refusal."""
        patcher = _tool(self.patch_tool)
        path = Path(wav_path)
        if path.is_symlink():
            raise self._refuse(f"{path}: refusing to read a replacement through a symlink", "wav")
        if not path.is_file():
            raise self._refuse(f"{path}: not a regular file", "wav")
        wav = self._run("wav", lambda: patcher.parse_wav(path.read_bytes()))
        slot = target.data
        frames = wav["frames"]
        if wav["rate"] != int(slot["sample_rate"]):
            frames = max(1, int(math.floor(frames * int(slot["sample_rate"]) / wav["rate"])))
        return {"rate": wav["rate"], "channels": wav["channels"], "source_frames": wav["frames"],
                "frames": frames, "seconds": frames / int(slot["sample_rate"]),
                "capacity_seconds": self.capacity_seconds(slot), "fits": frames <= int(slot["max_frames"]),
                "resampled": wav["rate"] != int(slot["sample_rate"])}

    def check_edit(self, target, values, staged=()):
        wav = values.get("wav")
        if not wav:
            return "Choose a WAV file for this slot."
        try:
            info = self.describe_wav(target, Path(wav))
        except LaneRefusal as exc:
            return f"{exc}"
        slot = target.data
        if info["channels"] != int(slot["channels"]):
            want = "mono" if int(slot["channels"]) == 1 else "stereo"
            return (f"{slot.get('name')} is a {want} slot but the WAV has {info['channels']} channel(s); "
                    f"supply {want} audio.")
        if not info["fits"]:
            return (f"Your WAV is {info['seconds']:.2f} s at {slot['sample_rate']} Hz but the slot holds "
                    f"{info['capacity_seconds']:.2f} s ({slot['max_frames']:,} frames). This writer never grows a "
                    "slot; shorten the audio or choose a slot with more room.")
        for other in staged:
            if other.lane_id == self.id and other.target_key == target.key:
                return "This slot is already in the recipe; remove that edit first to change it."
        return None

    def edit_summary(self, target, values):
        return f"{target.label} ← {Path(str(values.get('wav', ''))).name}"

    def compose_recipes(self, catalogue, edits, context):
        replacements = [{"slot": edit.target_key, "wav": str(Path(edit.values["wav"]).resolve())} for edit in edits]
        if not replacements:
            return []
        return [RecipeStep(self.id, {"schema": self.recipe_schema, "replacements": replacements},
                           f"{_plural(len(replacements), 'sound')}", len(replacements))]

    def _prepared(self, patcher, source, recipe, catalogue_path):
        catalogue = self.load_catalogue(catalogue_path)
        requests = [(str(row["slot"]), Path(row["wav"])) for row in recipe.get("replacements", [])]
        return self._run("plan", lambda: patcher.plan(Path(source), requests, catalogue))

    def plan(self, source, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        prepared = self._prepared(patcher, source, recipe, catalogue_path)
        items = [{k: v for k, v in item.items() if not k.startswith("_")} for item in prepared["items"]]
        payload = sum(int(item["video_bytes"]) for item in items)
        return PlanResult(self.id, len(items),
                          f"{_plural(len(items), 'sound')} encoded · {payload:,} payload bytes would change · "
                          + "; ".join(f"{item['name']}: {item['frames_written']:,} of {item['max_frames']:,} frames"
                                      + (f" (resampled from {item['resampled_from']} Hz)" if item.get("resampled_from") else "")
                                      for item in items),
                          {"items": items})

    def apply(self, source, destination, recipe, catalogue_path, work_dir):
        patcher = _tool(self.patch_tool)
        prepared = self._prepared(patcher, source, recipe, catalogue_path)
        return self._run("write", lambda: patcher.apply(prepared, Path(source), Path(destination), work_dir=work_dir))

    def verify(self, source, destination, receipt, recipe, catalogue_path, work_dir):
        verifier = _tool(self.verify_tool)
        report = self._run("verify", lambda: verifier.verify(
            Path(source), Path(destination), receipt, wav_dir=None, run_iso_verifier=True))
        passed = str(report.get("verdict", "")).lower() == "pass"
        iso_check = report.get("iso9660_verifier") or {}
        if iso_check.get("ran") and not iso_check.get("passed"):
            passed = False
        return Verdict(self.id, passed,
                       f"audio verifier: {report.get('verdict', '?')} · {report.get('declared_slots', 0)} slots checked · "
                       f"{report.get('changed_bytes', 0):,} bytes changed, {report.get('changed_outside_declared_spans', 0)} "
                       f"outside the declared spans · tree identical: {report.get('tree_identical')} · "
                       f"ISO9660 verifier: {'PASS' if iso_check.get('passed') else iso_check.get('reason', 'not run')}",
                       report)

    def receipt_summary(self, receipt):
        rows = receipt.get("replacements", [])
        return f"{_plural(len(rows), 'sound')} · {sum(int(r.get('video_bytes', 0)) for r in rows):,} payload bytes changed"


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

LANES: Dict[str, Lane] = {lane.id: lane for lane in (
    TextLane(), PlaybooksLane(), ColorsLane(), RosterLane(), StadiumLane(), AudioLane())}


def lanes_in_order() -> Tuple[Lane, ...]:
    return tuple(LANES[lane_id] for lane_id in LANE_ORDER)


def lane(lane_id: str) -> Lane:
    try:
        return LANES[lane_id]
    except KeyError as exc:
        raise Ps2DiscStudioError(f"{lane_id!r} is not one of the six PS2 lanes.") from exc


@functools.lru_cache(maxsize=1)
def _registry_rows() -> Dict[str, dict]:
    try:
        from mod_editor.core.capabilities import CapabilityRegistryLoader
        registry = CapabilityRegistryLoader().load(check_files=False)
    except Exception:
        return {}
    rows = {}
    for capability in getattr(registry, "capabilities", ()):
        raw = getattr(capability, "raw", None)
        if isinstance(raw, dict) and raw.get("id"):
            rows[str(raw["id"])] = raw
    return rows


def registry_rules(lane_id: str) -> List[str]:
    """The lane's ``input_constraints`` from its registry row, for the tab's Rules list."""
    row = _registry_rows().get(lane(lane_id).registry_id, {})
    return [str(item) for item in row.get("input_constraints", []) if str(item).strip()]


def registry_scope(lane_id: str) -> str:
    """The lane's runtime scope sentence (what is and is not proved)."""
    row = _registry_rows().get(lane(lane_id).registry_id, {})
    return str(row.get("runtime", {}).get("scope", "")).strip()


__all__ = [
    "AudioLane", "CatalogueScope", "ColorsLane", "DEFAULT_SCOPE", "FACE_SHIELD_LABELS", "LANES",
    "LANE_ORDER", "Lane", "LaneRefusal", "MAX_CUSTOM_NAME_CHARS", "PlanResult", "PlaybooksLane",
    "Ps2DiscStudioError", "RecipeContext", "RecipeStep", "RosterLane", "SERIAL", "StadiumLane",
    "StagedEdit", "Target", "TextLane", "Verdict", "binary32", "clean_custom_name", "describe_selector",
    "lane", "lanes_in_order", "registry_rules", "registry_scope", "tool_path",
]
