"""Shared captions for the beta-62 Build and Gameplay controls."""
from mod_editor.core import nfl2k5_throw_tuning as tt

SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Uses the Raiders at Texans "
    "broadcast layout with neutral panels, white scores, a red down box and a "
    "light clock strip. A scorebar folder overrides this with your painted "
    "template. Moves the kick meter up and hides the lineup strip. "
    "EXPERIMENTAL / UNWITNESSED; fonts and colours still differ.")
SCOREBUG_RUNTIME_HELP = (
    "Retail: Uses the original team panels. Patch: Adds team gradients, logos, "
    "small wordmarks and live timeout marks to the experimental scorebar. "
    "Diagnostic only and off in every preset. EXPERIMENTAL / UNWITNESSED; "
    "the game-entry freeze remains unresolved. Keep the six probe choices.")
PRACTICE_HELP = (
    "Retail: Practice is available from Game Modes. Patch: adds Practice below Schedule on the Coach's Desk. "
    "Practice uses your franchise roster and returns to the Coach's Desk when you quit. "
    "EXPERIMENTAL / UNWITNESSED: verify the return and unchanged schedule, roster and depth chart.")
ZONE_HELP = (
    "EXPERIMENTAL / UNWITNESSED. Retail: a shallow deep-zone corner can start by running. "
    "Patch: cap the initial depth request. Later movement can still turn him away. "
    "This does not add bail technique or change ball reaction.")
FRANCHISE_HELP = (
    "Retail: Owned players form the game roster and IR has no in-season returns. Patch: 2026 franchise rules "
    "are not available yet. Saved counters and correct player results still need integration. EXPERIMENTAL / UNWITNESSED.")
OPTIONS = (
    ("momentum_collisions", "Weight and speed in contact (experimental)", tt.momentum_patch.COLLISION_HELP_TEXT),
    ("read_option_runtime", "Read option mesh controls (experimental)", tt.read_option_patch.HELP_TEXT),
    ("screen_hooks", "Screen pass timing hooks (second experiment)", tt.screen_hooks_patch.HELP_TEXT),
    ("franchise_2026_rules", "2026 franchise rules (unavailable)", FRANCHISE_HELP),
    ("senior_bowl", "Senior Bowl native event (not available)", tt.senior_bowl_patch.HELP_TEXT),
    ("guardian_overlay", "Guardian caps (experimental)", tt.guardian_overlay_patch.HELP_TEXT),
    ("my_career", "MyCareer (experimental)", tt.my_career_patch.HELP_TEXT),
    ("crib_reclaim", "Crib movie cut (experimental)",
     "EXPERIMENTAL / UNWITNESSED. Retail: The Crib includes 23 movies. Patch: Remove those movies from a smaller image. "
     "The Trophy Room, awards, profiles, shared room, games and furniture stay."),
    ("modern_naming", "Modern 2K mode names (MyNFL, MyPlayer, Play Now)", tt.modern_naming_patch.HELP_TEXT),
    ("reserves_16", "16 reserves (experimental)",
     "Retail: 65 player slots per team. Patch: 16 reserves in a migrated save; an explicitly eligible team may hold 17. "
     "EXPERIMENTAL / UNWITNESSED. Build a paired disc and keep the original save."),
    ("created_teams_extra", "Two extra created teams (experimental)",
     "Retail: two created-team records. Patch: two more records with separate names and inherited stock assets. "
     "EXPERIMENTAL / UNWITNESSED. The franchise league stays at 32 teams."),
)
KEYS = tuple(row[0] for row in OPTIONS)
UNAVAILABLE = {"franchise_2026_rules": FRANCHISE_HELP, "senior_bowl": tt.senior_bowl_patch.NATIVE_BLOCKER}
HIRES_FAMILIES = (
    ("helmets", "All teams' helmets (experimental)"),
    ("field_logos", "Created-team midfield logos (experimental)"),
    ("stock_fields", "Stock midfield logos (experimental)"),
    ("scorebug", "Scorebug art (experimental)"),
    ("numbers", "Uniform numbers (experimental)"),
    ("jerseys", "Jerseys, clean and muddy (experimental)"),
)
