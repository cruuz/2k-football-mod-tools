"""Shared captions for the beta-62 Build and Gameplay controls."""
from mod_editor.core import nfl2k5_throw_tuning as tt

UNIFORM_CHOICE_HELP = (
    "Gameplay Patches selects the choice form for a new patch; the caption names the current form. "
    "Build also offers rule: fixed home dark / away white, with no in-game colour choice. "
    "The choice form uses the existing jersey-era up/down controls on Controller Assign "
    "and exhibition Team Select. Next past the last available era flips that side's colour "
    "and returns to era 0; previous below era 0 flips and goes to the last available era. "
    "Only available eras count. The initial colours follow the retail Cowboys rule. "
    "Team Select preview art shows the era only; check the uniforms on the field. "
    "Practice and Xbox Live do not gain a jersey-choice control. "
    "X_Ray reports that jersey choice did not work. The screen handlers and kit letters "
    "pass bounded native checks; his cause remains unresolved. EXPERIMENTAL / UNWITNESSED.")


def uniform_choice_caption(mode):
    """Name the installed/selected form without turning a status into a guess."""
    return {
        "choice": "Jersey choice: choice form (Controller Assign / exhibition Team Select)",
        "rule": "Jersey colour: rule form (fixed home dark / away white)",
        "": "Jersey choice: off (retail colours)",
        None: "Jersey colour: installed form unknown; inspect or rebuild from original source",
    }.get(mode, "Jersey colour: unrecognized form")


SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Uses each team's primary "
    "color on its panel with readable white scores and yellow possession highlighting; "
    "each outline uses a team colour that differs from its panel, or silver when no "
    "suitable colour is available, and the centre and decorative timeout marks stay neutral. "
    "The red down box and separate clock cells stay visible through the play "
    "with live values. The play clock shows -- when unavailable. Ball-on "
    "and event labels replace the down text while the clock cells stay visible. "
    "A scorebar folder selects your painted template (the v10 layout). Moves the kick meter up and hides the "
    "lineup strip. EXPERIMENTAL / UNWITNESSED (the outline revision is unwitnessed); rebuild from a clean source.")
SCOREBUG_RUNTIME_HELP = (
    "Retail: the ESPN scorebar stays static. Patch: the bar becomes the 2026 Monday Night Football "
    "broadcast bug. Team logos on their colours in the wings, the down plate in the possessing team's "
    "colour, timeout dashes under the scores, a white clock capsule with the play clock turning ESPN red "
    "under five seconds, and ESPN digits painted into the game's own HUD fonts. Adds 66 small textures "
    "to the HUD (0.35 MB). The beta 69 version added 1.7 MB, and that is what froze the game after "
    "Berman's intro: the resource loader ran out of room and read a chunk into a null buffer, reproduced "
    "in the emulator on 2026-09-15 (andrethealchemist: 'if you go into situation mode instead of play "
    "now/franchise, (bypassing Berman) you can see how cool the scorebug effects looks in game'). Needs "
    "the ESPN scorebar option and a disc image. Experimental, not yet witnessed in game."
)
PRACTICE_HELP = (
    "Retail: Practice is available from Game Modes. Patch: adds Practice below Schedule on the Coach's Desk. "
    "Practice uses your franchise roster and returns to the Coach's Desk when you quit. "
    "EXPERIMENTAL / UNWITNESSED: verify the return and unchanged schedule, roster and depth chart.")
ZONE_HELP = (
    "EXPERIMENTAL / UNWITNESSED. Retail: a shallow deep-zone corner can start by running. "
    "Patch: cap the initial depth request. Later movement can still turn him away. "
    "This does not add bail technique or change ball reaction.")
FRANCHISE_HELP = tt.franchise_2026_patch.UI_TEXT
OPTIONS = (
    ("momentum_collisions", "Weight and speed in contact (experimental)", tt.momentum_patch.COLLISION_HELP_TEXT),
    ("read_option_runtime", "Read option mesh controls (experimental)", tt.read_option_patch.HELP_TEXT),
    ("screen_hooks", "Screen pass timing hooks (second experiment)", tt.screen_hooks_patch.HELP_TEXT),
    ("coverage_trail", "Close pursuit recovery (experimental)", tt.coverage_trail_patch.HELP_TEXT),
    ("franchise_edit_player", "Franchise Edit Player (experimental)", tt.franchise_edit_player_patch.HELP_TEXT),
    ("cpu_money_downs", tt.cpu_money_downs_patch.BUILD_CAPTION, tt.cpu_money_downs_patch.HELP_TEXT),
    ("accelerated_clock", tt.accelerated_clock_patch.BUILD_CAPTION, tt.accelerated_clock_patch.HELP_TEXT),
    ("playbook_pair", "Separate offensive and defensive playbooks (experimental)", tt.playbook_pair_patch.HELP_TEXT),
    ("deep_zone_facing", "Deep-zone QB facing (experimental)",
     "Retail: corners can turn to run. Patch: try a slower QB-facing deep drop until a pass, run, or the selected "
     "receiver gets beyond the corner. EXPERIMENTAL / UNWITNESSED."),
    ("deep_zone_bail", "Press corner bail (experimental)",
     "Retail: the selected call keeps its starting alignment. Patch: use a selected three-deep press start and "
     "directional bail. Ends at seven yards when used alone. EXPERIMENTAL / UNWITNESSED."),
    ("weekly_prep", "Fix safety drills (experimental)",
     "EXPERIMENTAL / UNWITNESSED. Retail: DB drills skip both safety positions. "
     "Patch: include safeties in the same drills as corners. TE drill rows already exist."),
    ("weekly_prep_cpu", "CPU teams prepare too",
     "EXPERIMENTAL / UNWITNESSED. Retail: CPU clubs skip weekly prep. Patch: run "
     "the native routine before their games with equal low full-drill time for "
     "starters and backups, then two rest days. Weekly Preparation must be On."),
    ("weekly_prep_remember", "Remember my weekly prep",
     "EXPERIMENTAL / UNWITNESSED. Retail: only marked repeat activities survive "
     "weekly cleanup and the next season clears the plan. Patch: keep valid "
     "activities and apply your saved plan before games until you change it. "
     "Weekly Preparation must be On. An empty plan does nothing."),
    ("franchise_2026_rules", "2026 franchise rules (unavailable)", FRANCHISE_HELP),
    ("senior_bowl", "Senior Bowl native event (not available)", tt.senior_bowl_patch.HELP_TEXT),
    ("guardian_overlay", "Guardian caps (experimental)", tt.guardian_overlay_patch.HELP_TEXT),
    ("my_career", "MyCareer: draft and upgrades", tt.my_career_patch.HELP_TEXT),
    ("franchise_autosave", "Franchise Auto Save (experimental)", tt.franchise_autosave_patch.HELP_TEXT),
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
OPTIONS += (
    ("coin_defer", tt.coin_defer_patch.BUILD_CAPTION, tt.coin_defer_patch.HELP_TEXT),
    ("decided_clock", tt.decided_clock_patch.BUILD_CAPTION, tt.decided_clock_patch.HELP_TEXT),
)
KEYS = tuple(row[0] for row in OPTIONS)
# String-valued option rows: the checkbox means "not retail"; the adjacent combo picks the level.
# Parent option -> child options: unchecking the parent clears the children; checking a child checks the parent.
CHILDREN = {"weekly_prep": ("weekly_prep_cpu", "weekly_prep_remember")}
LEVELS = {"cpu_money_downs": (("Retail", "retail"), ("Modern", "modern"), ("Aggressive", "aggressive"))}
UNAVAILABLE = {"franchise_2026_rules": FRANCHISE_HELP, "senior_bowl": tt.senior_bowl_patch.NATIVE_BLOCKER}
HIRES_FAMILIES = (
    ("helmets", "All teams' helmets (experimental)"),
    ("field_logos", "Created-team midfield logos (experimental)"),
    ("stock_fields", "Stock midfield logos (experimental)"),
    ("scorebug", "Scorebug art (experimental)"),
    ("numbers", "Uniform numbers (experimental)"),
    ("jerseys", "Jerseys, clean and muddy (experimental)"),
)
