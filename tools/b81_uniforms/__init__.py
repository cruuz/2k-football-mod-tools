"""b81-uniforms authoring tools (beta 81, Noah 2026-11-18): the 2026 uniform pass and the jersey relief prototype.

Not part of a release (not in the release allowlist): they need the user's own retail disc, a built SOFTDRINK disc, the
reference frame library, Blender 4.0 on a private Xvfb and, for the emulator stills, a private xemu harness. Paths point
at the job's scratch folder (.b77-scratch/b81/uniforms); they are kept here so the work can be repeated.

  export_kits, dump_body, uvpos      every kit package of a disc as PNGs; the player body; where each texel sits on it
  render_kits, sheets, px, gaptable  renders on the player model, the audit sheets, colour sampling, the ranked gap table
  paintlib, unslant                  stripes placed by the model's own surface; a slanted digit set stood upright
  ../b81_uniform_pass.py             the two documents the Studio applies (kit textures as runs, digits as PNGs)
  mk_after, showcase, cards_unif     the corrected kit folders, one before/after image per kit, Team Select uniform cards
  bump_modern, bump_apply, bump_*    the jersey relief prototype: the map, its import into a disc copy, previews, report
  game_route.py, game_run.sh         one private emulator game (CPU v CPU) with stills from the pregame scenes on
  contact, gcrop                     labelled contact sheets and crops of those stills
"""
