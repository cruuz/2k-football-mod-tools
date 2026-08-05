#!/usr/bin/env python3
"""Show one generated contact sheet briefly for Spark visual verification."""

from pathlib import Path
import sys

import bpy


if "--" not in sys.argv or len(sys.argv[sys.argv.index("--") + 1 :]) != 1:
    raise RuntimeError("expected one contact-sheet path")
path = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
if not path.is_file():
    raise RuntimeError(f"contact sheet missing: {path}")
image = bpy.data.images.load(str(path), check_existing=False)
screen = bpy.context.screen
if screen is None:
    if not bpy.data.screens:
        raise RuntimeError("Blender file contains no screen layout")
    screen = bpy.data.screens[0]
for area in screen.areas:
    if area.type == "VIEW_3D":
        area.type = "IMAGE_EDITOR"
        area.spaces.active.image = image
        break
review_scene = path.parent / f"review-{path.stem}.blend"
# This is a disposable visual-review scene.  Reuse its fixed path so repeated
# release-gate checks do not accumulate stale multi-megabyte .blend files.
bpy.ops.wm.save_as_mainfile(filepath=str(review_scene))


def close_review() -> None:
    bpy.ops.wm.quit_blender()
    return None


if not bpy.app.background:
    bpy.app.timers.register(close_review, first_interval=60.0)
