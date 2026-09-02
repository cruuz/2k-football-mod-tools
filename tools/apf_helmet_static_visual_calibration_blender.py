#!/usr/bin/env python3
"""Strict Blender background entry point for non-package-bound calibration."""

from __future__ import annotations

from pathlib import Path
import sys
import traceback


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_helmet_static_visual_proof_blender as renderer


if __name__ == "__main__":
    receipt: Path | None = None
    try:
        receipt = renderer.arguments()
        renderer.render_receipt(
            receipt,
            "apf2k8_helmet_static_visual_calibration/v1",
            "calibration_not_package_bound",
        )
    except BaseException:
        renderer.write_error_log(receipt, traceback.format_exc())
        raise
