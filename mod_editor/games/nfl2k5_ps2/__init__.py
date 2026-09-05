"""ESPN NFL 2K5 (PlayStation 2) on the game-module contract.

This package is an *adapter*: it expresses the shipped PS2 lane on
:mod:`mod_editor.games.contract` without changing one line of the lane.  The
catalogue tool, patcher and independent verifier it wraps are imported from
``tools/`` exactly as ``mod_editor/core/ps2_disc_service.py`` imports its
tools; the three PS2 windows are exposed as window specs whose factories
import the shipped dialogs lazily.  Nothing upstream imports this package --
the core discovers it.

What is on the contract today:

* identity -- ``SLUS-20919`` and the two retail digests the registry pins,
  through the shared :mod:`mod_editor.games._formats.ps2_disc` identifier;
* one lane, ``colors.unif_words`` (registry row
  ``nfl2k5ps2.colors.unif_words``): the on-disc facemask/turtleneck colour
  writer, plan → build → verify on a copy of the user's own disc;
* three windows -- the PS2 save editor, the PS2 disc inventory and the PS2
  replacement-pack export -- so the chooser can open them.

The other eight registry rows stay exactly where they are; the fragment beside
this file carries all nine so the registry-merge proof covers the whole game.

A lane joins ``GAME.lanes`` when its registry row is in the fragment: the
executable-patch lane (``code_patches.py``) is complete as an interface and
proved on a synthetic ELF, but its row (``nfl2k5ps2.gameplay.executable_patches``,
classification ``unknown``) is a proposal until the maintainer applies it, so
until then it is reachable as :data:`CODE_PATCH_LANE` and covered by its own
tests rather than listed as a capability the module claims.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Optional, Sequence

from mod_editor.games._formats.ps2_disc import Ps2DiscIdentifier
from mod_editor.games.contract import (
    CONTRACT_SCHEMA,
    Catalogue,
    DeclaredRange,
    Edit,
    GameIdentity,
    GameModule,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    WindowSpec,
    load_manifest,
    require,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_disc_inventory as inventory_lib  # noqa: E402
import nfl2k5_ps2_unif_color_patch as colour_patch  # noqa: E402
import nfl2k5_ps2_unif_color_target_catalog as colour_catalog  # noqa: E402
import nfl2k5_ps2_unif_color_verify as colour_verify  # noqa: E402

GAME_ID = "nfl2k5_ps2"
SERIAL = inventory_lib.SERIAL

IDENTITY = GameIdentity(
    game_id=GAME_ID,
    title="ESPN NFL 2K5 (USA, PlayStation 2)",
    platform="PlayStation 2",
    serials=(SERIAL,),
    executable_sha256=(inventory_lib.RETAIL_BOOT_ELF_SHA256,),
    content_sha256=(inventory_lib.RETAIL_IMAGE_SHA256,),
)

_SIDES = {"H": "home", "A": "away"}


def _describe_selector(selector: str) -> str:
    if len(selector) == 4 and selector[:2].isdigit() and selector[3].isdigit():
        side = _SIDES.get(selector[2], selector[2])
        return f"uniform package {int(selector[:2])} · {side} · variant {selector[3]}"
    return f"uniform record {selector}"


class UnifColourLane:
    """The facemask/turtleneck colour writer, wrapped without change."""

    lane_id = "colors.unif_words"
    capability_id = "nfl2k5ps2.colors.unif_words"
    surface = "colors"
    title = "Facemask and turtleneck packed colours"
    classification = "offline-writer-proved"
    recipe_schema = colour_patch.RECIPE_SCHEMA
    validators = (
        "tools/validate_nfl2k5_ps2_unif_color.sh",
        "tools/validate_nfl2k5_ps2_unif_color.bat",
    )
    fixed_allocation = True
    budget = "two 4-byte packed ARGB words (facemask, turtleneck); exactly 4 bytes each, never longer"

    _WORDS = tuple(colour_catalog.WORD_NAMES)

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        tick = (lambda count: progress(f"{count} uniform records catalogued…")) if progress else None
        try:
            document = colour_catalog.build_catalog(str(source), progress=tick)
        except (colour_catalog.CatalogError, ValueError, OSError) as exc:
            raise Refusal(str(exc).strip() or exc.__class__.__name__) from exc
        targets = []
        for row in document["targets"]:
            key = row["selector"] or f"outer:{row['outer_index']}"
            targets.append(Target(
                key=key,
                label=f"{key} — {_describe_selector(key)}",
                detail=f"{row['iso_path']} · chunk offset 0x{row['colour_offset_in_chunk']:x}",
                budget=self.budget,
                searchable=f"{key} {_describe_selector(key)} {row['iso_path']}",
                raw=row,
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
        unknown = sorted(set(values) - set(self._WORDS))
        if unknown:
            return (
                f"{target.key}: {', '.join(unknown)} is not a word this writer edits; "
                f"choose facemask, turtleneck or both."
            )
        chosen = {name: values[name] for name in self._WORDS if values.get(name) is not None}
        if not chosen:
            return f"{target.key}: give a facemask colour, a turtleneck colour or both."
        for name, literal in chosen.items():
            try:
                colour_catalog.parse_color(str(literal))
            except colour_catalog.CatalogError as exc:
                return (
                    f"{target.key} {name}: {exc}. Use #RRGGBB or AARRGGBB — a packed "
                    f"colour word is exactly 4 bytes, so a longer literal cannot fit."
                )
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: dict[str, Any] = {"selector": edit.target_key}
            for name in self._WORDS:
                if edit.values.get(name) is not None:
                    row[name] = edit.values[name]
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": self.recipe_schema, "edits": rows}

    # -- plan / build / verify -----------------------------------------

    @staticmethod
    def _parse(recipe: Mapping[str, Any]) -> list:
        try:
            return colour_patch.parse_recipe(dict(recipe))
        except colour_patch.ColorPatchError as exc:
            raise Refusal(str(exc)) from exc

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        parsed = self._parse(recipe)
        try:
            prepared = colour_patch.plan(Path(source), parsed, dict(catalogue.document))
        except (colour_patch.ColorPatchError, colour_catalog.CatalogError, ValueError, OSError) as exc:
            raise Refusal(str(exc).strip() or exc.__class__.__name__) from exc
        edits = prepared["edits"]
        return Plan(
            lane_id=self.lane_id,
            target_keys=tuple(item["selector"] for item in edits),
            declared_ranges=tuple(
                DeclaredRange(int(item["offset_in_iso"]), int(item["span_size"]),
                              f"unif_color:{item['selector']}")
                for item in edits
            ),
            document={
                "serial": prepared["serial"],
                "edits": [
                    {key: value for key, value in item.items() if key != "replacement"}
                    for item in edits
                ],
                "files": sorted(prepared["by_file"]),
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
        source = Path(source)
        destination = Path(destination)
        require(
            destination.resolve() != source.resolve(),
            f"{destination} is the source image; a build writes a NEW image and never the source.",
        )
        require(
            not destination.exists(),
            f"destination {destination} already exists; refusing to overwrite an image",
        )
        parsed = self._parse(recipe)
        try:
            receipt = colour_patch.apply(
                source, destination, parsed,
                pinned_catalog=dict(catalogue.document),
                work_dir=work_dir,
            )
        except (colour_patch.ColorPatchError, colour_catalog.CatalogError, ValueError, OSError) as exc:
            raise Refusal(str(exc).strip() or exc.__class__.__name__) from exc
        return Receipt(
            schema=receipt["schema"],
            lane_id=self.lane_id,
            source=str(source),
            destination=str(destination),
            declared_ranges=tuple(
                DeclaredRange(int(item["start"]), int(item["length"]), str(item["reason"]))
                for item in receipt["declared_ranges"]
            ),
            document=receipt,
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        try:
            report = colour_verify.verify(Path(source), Path(destination), dict(receipt.document))
        except AssertionError as exc:  # ColorVerifyError and IsoVerifyError
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        except (ValueError, OSError) as exc:
            return Verdict(False, f"Verification could not run: {exc}", {"error": str(exc)})
        return Verdict(
            report.get("result") == "PASS",
            f"{report['edits_checked']} edit(s) verified; {report['unif_records_decoded']} Unif "
            f"records decoded; {report['unchanged_bytes_compared']:,} unchanged bytes compared.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "nfl2k5-ps2-unif-synthetic.iso"
        path.write_bytes(colour_catalog.build_synthetic_iso())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        return (Edit("18H0", {"facemask": "#00FF00"}, note="conformance"),)


# --------------------------------------------------------------------------
# Windows: the four shipped PS2 dialogs, imported only when opened. The Disc
# Studio comes first: it is where the disc is edited; the rest read or export.
# --------------------------------------------------------------------------

def _disc_studio(parent: Any = None, **context: Any) -> Any:
    from mod_editor.gui.ps2_disc_studio_qt import Ps2DiscStudioDialog

    iso = context.get("iso")
    return Ps2DiscStudioDialog(parent=parent, initial_iso=Path(iso) if iso else None)


def _save_editor(parent: Any = None, **_context: Any) -> Any:
    from mod_editor.gui.ps2_save_dialog_qt import Ps2SaveEditorDialog

    return Ps2SaveEditorDialog(parent=parent)


def _disc_inventory(parent: Any = None, **_context: Any) -> Any:
    from mod_editor.gui.ps2_disc_dialog_qt import Ps2DiscInventoryDialog

    return Ps2DiscInventoryDialog(parent=parent)


def _replacement_pack_export(parent: Any = None, **context: Any) -> Any:
    from mod_editor.gui.ps2_export_dialog_qt import Ps2ExportDialog

    return Ps2ExportDialog(context.get("facade", context.get("project")), parent=parent)


WINDOWS = (
    WindowSpec(
        window_id="disc-studio",
        menu_label="PS2 NFL 2K5 Studio…",
        tooltip=(
            "Edit an ESPN NFL 2K5 PlayStation 2 disc: menu text, playbooks, uniform colours, the disc roster, "
            "stadium positions and audio slots, then build a new ISO with receipts. Your own disc image is never written."
        ),
        flag="ps2-disc-studio",
        factory=_disc_studio,
    ),
    WindowSpec(
        window_id="save-editor",
        menu_label="PS2 Save Editor…",
        tooltip="Edit an ESPN NFL 2K5 PlayStation 2 memory-card save. Your Xbox project is not touched.",
        flag="ps2-save",
        factory=_save_editor,
    ),
    WindowSpec(
        window_id="disc-inventory",
        menu_label="PS2 Disc Inventory…",
        tooltip="Browse every named resource on an ESPN NFL 2K5 PlayStation 2 disc, read-only.",
        flag="ps2-disc",
        factory=_disc_inventory,
    ),
    WindowSpec(
        window_id="replacement-pack",
        menu_label="Export PS2 replacement pack…",
        tooltip="Export the open Xbox project's edited uniform textures as a PCSX2 replacement pack.",
        flag="ps2-export",
        factory=_replacement_pack_export,
        needs_studio_session=True,
    ),
)

def _code_patch_lane():
    """The executable-patch lane: interface complete, every translation refused today.

    Imported lazily so ``python -m mod_editor.games.nfl2k5_ps2.code_patches``
    does not import the module twice (once through this package, once as
    ``__main__``); ``CODE_PATCH_LANE`` is a module attribute resolved on demand.
    """

    from .code_patches import CAPABILITY_ID, Ps2CodePatchLane

    return Ps2CodePatchLane(IDENTITY), CAPABILITY_ID


def __getattr__(name: str):
    if name == "CODE_PATCH_LANE":
        return _code_patch_lane()[0]
    raise AttributeError(name)


def _registered(capability_id: str) -> bool:
    """Whether the registry fragment beside this file carries ``capability_id``."""

    try:
        document = json.loads((HERE / "registry.fragment.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(row.get("id") == capability_id for row in document.get("capabilities", []))


CODE_PATCH_CAPABILITY_ID = "nfl2k5ps2.gameplay.executable_patches"
LANES = (UnifColourLane(),) + ((_code_patch_lane()[0],) if _registered(CODE_PATCH_CAPABILITY_ID) else ())

GAME = GameModule(
    contract=CONTRACT_SCHEMA,
    identity=IDENTITY,
    identifier=Ps2DiscIdentifier(IDENTITY),
    lanes=LANES,
    windows=WINDOWS,
    manifest=load_manifest(HERE),
    package=__name__,
)

__all__ = ["CODE_PATCH_CAPABILITY_ID", "CODE_PATCH_LANE", "GAME", "GAME_ID", "IDENTITY", "LANES", "SERIAL", "UnifColourLane", "WINDOWS"]
