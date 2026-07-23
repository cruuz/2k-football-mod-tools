"""Launch or inspect the public-safe mod editor scaffold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .core.apf_digital_font import create_apf_digital_font_recipe
from .core.apf_export import export_apf_jersey
from .core.capabilities import CapabilityRegistryLoader
from .core.errors import ModEditorError
from .core.gameplay_inspection import (
    inspect_draft_priority,
    inspect_gameplay_sliders,
    inspect_nfl_franchise_limit,
    inspect_nfl_save_inventory,
)
from .core.menu_modes import inspect_main_menu
from .core.nfl_audio import create_nfl_menu_back_audio_recipe
from .core.presentation_inspection import inspect_apf_scorebug_presentation
from .core.recipes import (
    ScorebugRecipeEdit,
    create_apf_helmet_recipe,
    create_apf_jersey_recipe,
    create_apf_pants_recipe,
    create_apf_shoulder_recipe,
    create_nfl_scorebug_recipe,
)
from .core.uniform_sharing import (
    inspect_apf_helmet_sharing,
    inspect_apf_jersey_sharing,
    inspect_apf_pants_sharing,
    inspect_apf_shoulder_sharing,
    inspect_nfl_uniform_sharing,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--studio",
        action="store_true",
        help="open the 2K5 Mod Studio desktop application",
    )
    action.add_argument(
        "--check-registry",
        action="store_true",
        help="validate the capability registry without opening a display",
    )
    action.add_argument(
        "--export-apf-jersey",
        type=Path,
        metavar="NEW_OUTPUT_DIR",
        help=(
            "read one pinned retail APF jersey into a new PNG/provenance "
            "directory without opening the GUI or writing an archive"
        ),
    )
    action.add_argument(
        "--create-apf-jersey-recipe",
        type=Path,
        metavar="OUTPUT.json",
        help="create a canonical APF jersey recipe without opening the GUI",
    )
    action.add_argument(
        "--create-apf-helmet-recipe",
        type=Path,
        metavar="OUTPUT.json",
        help="create a canonical APF helmet two-channel recipe without opening the GUI",
    )
    action.add_argument(
        "--create-apf-pants-recipe",
        type=Path,
        metavar="OUTPUT.json",
        help="create a canonical APF pants recipe without opening the GUI",
    )
    action.add_argument(
        "--create-apf-shoulder-recipe",
        type=Path,
        metavar="OUTPUT.json",
        help="create a canonical APF shoulder-color recipe without opening the GUI",
    )
    action.add_argument(
        "--create-apf-digital-font-recipe",
        type=Path,
        metavar="OUTPUT.json",
        help="create a canonical APF shared alpha-only digital_font recipe without opening the GUI",
    )
    action.add_argument(
        "--create-nfl-menu-back-audio-recipe",
        type=Path,
        metavar="OUTPUT.json",
        help="create a canonical fixed-target NFL menu-back WAV recipe without opening the GUI",
    )
    action.add_argument(
        "--create-nfl-scorebug-recipe",
        type=Path,
        metavar="OUTPUT.json",
        help="create a canonical NFL scorebug recipe without opening the GUI",
    )
    action.add_argument(
        "--inspect-nfl-uniform-sharing",
        metavar="SELECTOR",
        help=(
            "list exact cross-team content aliases and independent physical "
            "ownership for an NFL selector such as 09A0"
        ),
    )
    action.add_argument(
        "--inspect-apf-jersey-sharing",
        type=int,
        metavar="ASSET_INDEX",
        help="list every APF team/bank selector affected by jersey asset 0..23",
    )
    action.add_argument(
        "--inspect-apf-pants-sharing",
        type=int,
        metavar="ASSET_INDEX",
        help="list every APF team/bank selector affected by pants asset 0..23",
    )
    action.add_argument(
        "--inspect-apf-helmet-sharing",
        type=int,
        metavar="ASSET_INDEX",
        help="list every APF team/bank selector affected by helmet asset 0..23",
    )
    action.add_argument(
        "--inspect-apf-shoulder-sharing",
        type=int,
        metavar="ASSET_INDEX",
        help="list every APF team/bank selector affected by shoulder asset 0..23",
    )
    action.add_argument(
        "--inspect-gameplay-sliders",
        choices=("nfl2k5", "apf2k8"),
        metavar="GAME",
        help=(
            "inspect the named 21-slider schema and proof boundary for "
            "nfl2k5 or apf2k8"
        ),
    )
    action.add_argument(
        "--inspect-draft-priority",
        choices=("nfl2k5", "apf2k8"),
        metavar="GAME",
        help=(
            "inspect named position weights and whether their CPU draft owner "
            "is proved for nfl2k5 or apf2k8"
        ),
    )
    action.add_argument(
        "--inspect-nfl-franchise-limit",
        choices=("draft", "trade", "salary-cap", "contracts", "super-bowl", "all"),
        metavar="TARGET",
        help=(
            "inspect a named NFL franchise feasibility target, or all five, "
            "without exposing patch offsets"
        ),
    )
    action.add_argument(
        "--inspect-nfl-save-inventory",
        action="store_true",
        help=(
            "show sanitized metadata and observed slider values from the "
            "pinned NFL Xbox save audit"
        ),
    )
    action.add_argument(
        "--inspect-main-menu",
        choices=("nfl2k5", "apf2k8"),
        metavar="GAME",
        help=(
            "show hash-pinned named Main Menu state/layout reachability for "
            "nfl2k5 or apf2k8"
        ),
    )
    action.add_argument(
        "--inspect-apf-scorebug",
        action="store_true",
        help="show named APF scorebug components and digital-font writer boundary",
    )
    parser.add_argument(
        "--require-registry",
        action="store_true",
        help="refuse the temporary sample fallback",
    )
    parser.add_argument(
        "--source-0a",
        type=Path,
        help="user-owned pinned retail APF 0A file, opened read-only for export",
    )
    parser.add_argument("--asset-index", type=int, help="APF uniform asset integer 0..23")
    parser.add_argument("--jersey-png", type=Path, help="exact 1024x1024 RGBA APF PNG")
    parser.add_argument(
        "--helmet-png",
        type=Path,
        help="exact 256x1024 RGBA APF PNG with R/G data, B=0, and A=255",
    )
    parser.add_argument(
        "--pants-png", type=Path, help="exact opaque 512x512 RGBA APF PNG"
    )
    parser.add_argument(
        "--shoulder-png", type=Path, help="exact 1024x1024 RGBA APF shoulder-color PNG"
    )
    parser.add_argument(
        "--apf-digital-font-png",
        type=Path,
        help="exact 128x128 RGBA APF digital_font PNG with solid-white RGB and stored alpha",
    )
    parser.add_argument(
        "--purpose",
        default="User-authored NFL 2K5 mod project.",
        help="human-readable NFL typed-recipe purpose",
    )
    parser.add_argument(
        "--audio-wav",
        type=Path,
        help="strict mono PCM16LE 16000 Hz, 5696-frame WAV for menu-back_01",
    )
    parser.add_argument("--score-buga-png", type=Path, help="64x64 RGBA scorebug atlas")
    parser.add_argument("--shield-espn-png", type=Path, help="128x64 RGBA ESPN strip")
    parser.add_argument("--digital-font-png", type=Path, help="128x128 RGBA digit atlas")
    args = parser.parse_args(argv)
    if args.check_registry:
        registry = CapabilityRegistryLoader().load(
            allow_sample_fallback=not args.require_registry
        )
        print(
            "MOD_EDITOR_REGISTRY_OK "
            f"capabilities={len(registry.capabilities)} "
            f"fallback={str(registry.used_sample_fallback).lower()}"
        )
        return 0
    if args.export_apf_jersey is not None:
        if args.source_0a is None or args.asset_index is None:
            parser.error("APF jersey export requires --source-0a and --asset-index 0..23")
        if not 0 <= args.asset_index <= 23:
            parser.error("APF jersey export --asset-index must be in 0..23")
        try:
            result = export_apf_jersey(
                source_0a=args.source_0a,
                asset_index=args.asset_index,
                output_dir=args.export_apf_jersey,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            "MOD_EDITOR_APF_JERSEY_EXPORT_CREATED "
            f"asset={result.asset_index} files={result.file_count} "
            "archive_written=false bank_labels=0,1 "
            f"provenance={result.provenance}"
        )
        return 0
    if args.create_apf_jersey_recipe is not None:
        if args.asset_index is None or args.jersey_png is None:
            parser.error("APF recipe creation requires --asset-index and --jersey-png")
        try:
            result = create_apf_jersey_recipe(
                output=args.create_apf_jersey_recipe,
                asset_index=args.asset_index,
                png=args.jersey_png,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"MOD_EDITOR_APF_JERSEY_RECIPE_CREATED path={result}")
        return 0
    if args.create_apf_pants_recipe is not None:
        if args.asset_index is None or args.pants_png is None:
            parser.error("APF pants recipe creation requires --asset-index and --pants-png")
        try:
            result = create_apf_pants_recipe(
                output=args.create_apf_pants_recipe,
                asset_index=args.asset_index,
                png=args.pants_png,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"MOD_EDITOR_APF_PANTS_RECIPE_CREATED path={result}")
        return 0
    if args.create_apf_helmet_recipe is not None:
        if args.asset_index is None or args.helmet_png is None:
            parser.error(
                "APF helmet recipe creation requires --asset-index and --helmet-png"
            )
        try:
            result = create_apf_helmet_recipe(
                output=args.create_apf_helmet_recipe,
                asset_index=args.asset_index,
                png=args.helmet_png,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"MOD_EDITOR_APF_HELMET_RECIPE_CREATED path={result}")
        return 0
    if args.create_apf_shoulder_recipe is not None:
        if args.asset_index is None or args.shoulder_png is None:
            parser.error(
                "APF shoulder recipe creation requires --asset-index and --shoulder-png"
            )
        try:
            result = create_apf_shoulder_recipe(
                output=args.create_apf_shoulder_recipe,
                asset_index=args.asset_index,
                png=args.shoulder_png,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"MOD_EDITOR_APF_SHOULDER_RECIPE_CREATED path={result}")
        return 0
    if args.create_apf_digital_font_recipe is not None:
        if args.apf_digital_font_png is None:
            parser.error(
                "APF digital_font recipe creation requires --apf-digital-font-png"
            )
        try:
            result = create_apf_digital_font_recipe(
                output=args.create_apf_digital_font_recipe,
                png=args.apf_digital_font_png,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"MOD_EDITOR_APF_DIGITAL_FONT_RECIPE_CREATED path={result}")
        return 0
    if args.create_nfl_menu_back_audio_recipe is not None:
        if args.audio_wav is None:
            parser.error("NFL menu-back audio recipe creation requires --audio-wav")
        try:
            result = create_nfl_menu_back_audio_recipe(
                output=args.create_nfl_menu_back_audio_recipe,
                purpose=args.purpose,
                wav=args.audio_wav,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"MOD_EDITOR_NFL_MENU_BACK_AUDIO_RECIPE_CREATED path={result}")
        return 0
    if args.create_nfl_scorebug_recipe is not None:
        selected = (
            ("score_buga", args.score_buga_png),
            ("shield_espn", args.shield_espn_png),
            ("digital_font", args.digital_font_png),
        )
        edits = [
            ScorebugRecipeEdit(target, path)
            for target, path in selected
            if path is not None
        ]
        if not edits:
            parser.error(
                "NFL scorebug recipe creation requires at least one of "
                "--score-buga-png, --shield-espn-png, or --digital-font-png"
            )
        try:
            result = create_nfl_scorebug_recipe(
                output=args.create_nfl_scorebug_recipe,
                purpose=args.purpose,
                edits=edits,
            )
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"MOD_EDITOR_NFL_SCOREBUG_RECIPE_CREATED path={result} targets={len(edits)}")
        return 0
    if args.inspect_nfl_uniform_sharing is not None:
        try:
            result = inspect_nfl_uniform_sharing(args.inspect_nfl_uniform_sharing)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_apf_jersey_sharing is not None:
        try:
            result = inspect_apf_jersey_sharing(args.inspect_apf_jersey_sharing)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_apf_pants_sharing is not None:
        try:
            result = inspect_apf_pants_sharing(args.inspect_apf_pants_sharing)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_apf_helmet_sharing is not None:
        try:
            result = inspect_apf_helmet_sharing(args.inspect_apf_helmet_sharing)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_apf_shoulder_sharing is not None:
        try:
            result = inspect_apf_shoulder_sharing(args.inspect_apf_shoulder_sharing)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_gameplay_sliders is not None:
        try:
            result = inspect_gameplay_sliders(args.inspect_gameplay_sliders)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_draft_priority is not None:
        try:
            result = inspect_draft_priority(args.inspect_draft_priority)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_nfl_franchise_limit is not None:
        try:
            result = inspect_nfl_franchise_limit(args.inspect_nfl_franchise_limit)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_nfl_save_inventory:
        try:
            result = inspect_nfl_save_inventory()
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_main_menu is not None:
        try:
            result = inspect_main_menu(args.inspect_main_menu)
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.inspect_apf_scorebug:
        try:
            result = inspect_apf_scorebug_presentation()
        except (ModEditorError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    # Product mode is the default GUI.  The explicit --studio form is retained
    # for desktop launchers and remains mutually exclusive with headless tools.
    from .core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
    from .core.nfl2k5_extended_visual_catalog import (
        load_nfl2k5_product_visual_catalog,
    )
    from .core.product_catalog import build_nfl2k5_product_catalog
    from .gui.studio_qt import launch_studio
    from .studio.facade import Nfl2k5StudioFacade

    registry = CapabilityRegistryLoader().load(
        allow_sample_fallback=False, check_files=False
    )
    product_catalog = build_nfl2k5_product_catalog(registry)
    uniform_catalog = load_nfl2k5_uniform_catalog()
    visual_catalog = load_nfl2k5_product_visual_catalog()
    facade = Nfl2k5StudioFacade(
        uniform_catalog=uniform_catalog,
        visual_catalog=visual_catalog,
    )
    return launch_studio(
        facade,
        product_catalog=product_catalog,
        uniform_catalog=uniform_catalog,
        extended_visual_catalog=visual_catalog.extended,
    )


if __name__ == "__main__":
    raise SystemExit(main())
