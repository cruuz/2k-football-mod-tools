"""Command-line entry point for the APF 2K8 Mod Studio desktop app."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__
from .gui import PRODUCT_NAME, launch_studio
from .models import ApfCategory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="apf2k8-mod-studio",
        description=(
            "Open the APF 2K8 Mod Studio desktop application. The optional "
            "source is an untouched APF ISO or extracted game folder."
        ),
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="optional APF ISO or extracted game folder to load after startup",
    )
    parser.add_argument(
        "--tab",
        choices=tuple(category.value for category in ApfCategory),
        default=ApfCategory.GETTING_STARTED.value,
        help=(
            "sidebar tab to open at startup; useful for returning directly to "
            "uniforms, audio, rosters, or the universal asset browser"
        ),
    )
    parser.add_argument(
        "--workspace",
        choices=("primary", "roster-planner", "soundtrack", "raw-assets"),
        default="primary",
        help=(
            "inner workspace to open at startup; roster-planner opens the "
            "53-player planning surface and soundtrack opens the 15-track "
            "paired soundtrack album directly"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PRODUCT_NAME} alpha ({__version__})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return launch_studio(
        initial_source=arguments.source,
        initial_category=ApfCategory(arguments.tab),
        initial_workspace=arguments.workspace,
    )


if __name__ == "__main__":
    raise SystemExit(main())
