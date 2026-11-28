"""b81-art authoring tools (beta 81, Noah 2026-11-18): the helmet and Team Select cleanup.

Not part of a release (not in the release allowlist): they need the user's own retail disc, a built SOFTDRINK disc, the
SOFTDRINK pack's source PNGs and Blender 4.0 with a private Xvfb. Scratch goes to ``B81_ART_WORK``.

Order of work (each file says more):
  cardlib, final, extra_kits   the league project's cards and helmets, their retail twins, the built disc's finished ones
  dump_head, geom, uvmap*      the Studio's head export with the modern shell; the Team Select card poses as UV maps
  reg, texdet*, fixtex*        official-logo registration, the old-logo / painted-vent / flag-outline detector, the fill
  make_tex, assign             the cleaned level-0 textures of every slot (Carolina: silver default, black on the blue alternate)
  ../b81_helmet_cleanup.py     the Studio's kit-fix document from them (data/nfl2k5_kit_fixes_2026_b81.json)
  bljob, render_all, post      tools/b765/u1_blender.py renders of the old and the cleaned helmet (the k2 card renderer)
  compose, make_cards, minis   the new cards and mini helmets: the shipped picture, changed only where the helmet changed
  showcase, apply_art          one before/after image per team; the new art put into an extracted source folder
"""
