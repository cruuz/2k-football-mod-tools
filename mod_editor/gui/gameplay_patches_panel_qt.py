"""Gameplay Patches tab: the executable patches that change how the game plays, in one place.

Each toggle explains what the retail game does, what the patch changes, and what to expect.
Writing goes through mod_editor.core.mod_build so a copy carries exactly the ticked patches and
one receipt.  The throw curve tables keep their own richer editor (Throw Distance & Arc).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.gui.ux_text import NOT_TESTED, XEMU_LINE, Details, plain_failure, show_operation_error, source_captions, suggest_copy_name, tab_title, write_caption

SOURCE_FILTER = "NFL 2K5 default.xbe or disc image (default.xbe *.xbe *.xiso *.iso *.img);;All files (*)"

PATCHES = (
    ("catch_slider", "Catching and Interception sliders decide the outcome",
     "Retail: the Catching slider barely reaches play and the Interception slider is scaled by difficulty "
     "and floored at a 10 % pick chance, which is why the forums call it broken. Patch: the catch roll is "
     "divided by twice the receiver's side's Catching slider (goes to 200) and a defender's roll by twice the "
     "Interception slider (0 = no picks, 50 = retail, 100 = double)."),
    ("accel_ramp", "Acceleration ramp",
     "Retail has no acceleration: everyone is at top speed on the first step, so linemen keep pace with "
     "receivers and slow quarterbacks burst out of the pocket. Patch: players wind up from 60 % to 100 % of "
     "their Speed rating, about 1 s at 99 Agility and 2 s at 30; standing still resets it."),
    ("draft_ai", "Realistic, unpredictable CPU drafts and free agency in franchise",
     "Retail: on the clock a CPU team takes the best raw overall among its neediest positions, and raw "
     "overall is compared across positions, so the positions whose rookies roll the highest overalls (HB, DE, "
     "T, QB) fill round 1 and the 11th-best HB goes as soon as HB is a top-three need. Patch: the pick is the "
     "prospect with the best edge over his own position's class average, times real positional value, plus "
     "the team's need order and a little noise; CPU free-agent targets are scored the same way."),
    ("returner_fix", "Real kick and punt returners on CPU depth charts",
     "Retail: the franchise auto depth chart never records which player had the best punt-return score; it "
     "stores the score itself as the roster slot, so the punt returner is whoever sits in slot 0 (often a QB), "
     "and the second kick returner is chosen on a stale score. Patch: returners are tracked by player over "
     "the whole roster, starters stay off the units unless nobody else is eligible, and only WR, CB, S, RB and "
     "FB can return."),
    ("progression", "NFL-shaped player development",
     "Retail: development is a hidden archetype per player driving flat aging curves (+2 or +3 from rookie "
     "year to the prime), so the draft-day rating is the career. Patch (data only): the ten aging-curve tables "
     "grow over years 1-5 by rating family and decline harder after year 9-12 (speed first), and each "
     "position's archetype mix is widened so more prospects become stars or busts. Draft-day ratings are "
     "unchanged."),
    ("team_column", "TEAM column on the franchise Player Card",
     "Retail: the Player Card lists a player's stats season by season (Yr, Games, ...) but never which team a "
     "season was played for; only the card's colours show the current team, so a traded veteran's history reads "
     "as one club. Patch: a TEAM column sits next to Yr (frozen, the stats still scroll). The current season shows "
     "the live team; every season rollover records the team the player finished it with, so from then on past "
     "seasons show that club (a mid-season trade shows the season-end team). Seasons that ended before this patch "
     "was in the save, the folded \"pre\" row and the Total row read \"--\". Franchise saves stay loadable either way."),
    ("kick_rules", "Modern kicking: kickoff from the 35, touchbacks to the 35, PAT from the 15, ~70-yard legs",
     "Retail kicks off from the 30 with touchbacks at the 20, snaps the extra point from the 2, and its "
     "field-goal tables top out near 60 yards for a 99 kicker on a perfect meter. Patch: kickoff spot 35, "
     "touchback 35 (2026 rule), PAT snapped from the 15 (two-point tries stay at the 2), and the meter and kicker "
     "curves re-spaced as a scale so a 99 leg reaches 65-69 yards while mid-power kickers gain 2-3. "
     "Kickoff and return formations follow the ball; onside and safety kicks are untouched; the CPU keeps "
     "its retail field-goal range for fourth-down decisions."),
    ("dynamic_kickoff", "Dynamic kickoff: nobody moves until the ball comes down, landing zone, CPU kicks and touchbacks (disc images only, experimental)",
     "Retail: on a kickoff everyone sprints at the kick, the ball is kicked wherever the CPU meter lands and a returner brings "
     "most kicks out. Patch: the 2024/2025 rule. The ten coverage men and nine setup blockers hold still until the ball touches the "
     "ground or a player (the kicker and the two returners are free); first contact in the landing zone (goal line to the 20) then "
     "downed in the end zone puts the ball on the 20, a kick straight into the end zone is a touchback to the 35 (30 for the 2024 "
     "spot), short of the landing zone or out of bounds is the 40; the CPU kicker aims for the landing zone 90 % of the time and the "
     "CPU returner takes the touchback 90 % of the time. Your own kicks and returns stay in your hands; onside and safety kicks are "
     "untouched. Switches on the modern kick spots and the dynamic line-up with it. Unwitnessed in game."),
    ("overtime", "Modern overtime: both teams get a possession, 10 minutes with ties, playoffs to a winner",
     "Retail overtime is sudden death for the quarter length: any score ends it, even a first-possession "
     "touchdown, and the regular season ties after one period. Patch (the 2025 NFL rule): each team is "
     "guaranteed a possession unless the kicking team scores a safety; after both have possessed the leader "
     "wins or the next score wins; regular-season overtime is one 10-minute period (scaled with the quarter "
     "length) and can tie; the postseason keeps playing, including through an unfinished second possession. "
     "The franchise sim engine gets the 10-minute clock and the one-period tie; its own sudden-death rule is "
     "left as is."),
    ("camera", "Default camera: Standard becomes the Far look",
     "Retail's Standard camera uses a 35 lens 8 yards behind the quarterback; the Far preset is the same "
     "geometry through a wider 28 lens (24 with the ball in the air). Patch: the seven live-play records of "
     "the Standard preset take Far's look-at, lens and offset words, so a profile left on Standard gets the "
     "Far view. Far itself, the kick, replay and other presets are untouched; the fresh-profile default stays "
     "Standard."),
    ("position_row", "Position on the first page of Edit Player (roster and Franchise)",
     "Retail: Create Player lets you pick a position, but Edit Player never lists it, in roster mode or in "
     "Franchise, so a position change means a new player. Patch: the Position row (the game's own picker, "
     "17 positions, ratings kept, overall recomputed from the new position) sits after Last Name on the first "
     "page of both Edit Player screens; Franchise opens the same screens. Run Depth Chart -> Auto afterwards. "
     "Unwitnessed in game."),
    ("probowl_order", "Pro Bowl Votes in football order",
     "Retail: the Pro Bowl Votes tabs run QB, HB, FB, WR, TE, C, G, T, then K and P before the defence. Patch: "
     "the tab list runs offence, defence, then K and P (one pointer list; the vote scanner reads each tab's "
     "own position, and no other screen uses the list). Unwitnessed in game."),
    ("penalties", "Penalties at NFL rates + a working Chop Block toggle",
     "Retail: every penalty slider drives a hidden curve table (a probability per block, a hazard while the ball "
     "is in flight, a grace window after the release), tuned so the default 50 flags far more holding, face masks "
     "and clipping than an NFL Sunday, the incidental face mask is still the 2004 five-yard call, and the Chop "
     "Block On/Off toggle does nothing (chop blocks follow the Clipping slider). Patch: seven curve tables are "
     "re-knotted in place so the default 50 lands near NFL 2024 per-game rates (0 still means none, 100 keeps the "
     "retail extreme), the incidental face mask becomes 15 yards, and the Chop Block toggle is wired through a "
     "10-byte stub so it really silences chop blocks (retail profiles have it Off: switch it On in Penalty "
     "Settings). The rates are ESTIMATED pending a calibration playtest; illegal formation, illegal contact and "
     "12 men do not exist in the engine. Unwitnessed in game."),
    ("uniform_choice", "Home/away jerseys at any stadium",
     "Retail: the jersey colour is decided once per game load by one rule (home dark, visitor white, except the "
     "Cowboys wear white at home and navy in Washington and Tennessee); the player only picks the era. Patch: "
     "the same up/down that picks the era on Controller Assign or Team Select keeps going past the last era to "
     "flip that side's colour and restart at the first era (15 eras x 2 colours per side; the retail default "
     "stays the default; both teams may choose white). Practice and Xbox Live keep the retail rule; the Team "
     "Select preview shows the era art only. Unwitnessed in game."),
    ("kick_laces", "Laces to the posts on field goals and PATs",
     "Retail: the holder's animation decides which way the ball faces on a place kick, and the hold clip "
     "leaves the laces toward the kicker (the kickoff tee is a code constant and already faces the posts). "
     "Patch: at the one point where every held-ball orientation path joins, a 143-byte cave in a dead routine "
     "checks that the play is live and the offence's formation is the Field Goal formation (PAT and FG; punts, "
     "kickoffs and scrimmage carries are not), then turns the ball 180 degrees about its own long axis with "
     "the game's quaternion product, so the laces face the posts through the hold and the kick. A fake field "
     "goal carries the rolled ball for that play only. Unwitnessed in game."),
    ("prospect_names", "Modern draft-prospect names (disc images only)",
     "Retail: rookies and free agents are named from the 1990 US Census lists (James, Harold, Walter... Smith, "
     "Garcia, Martinez), drawn independently, so a fifth of every draft class carries a Hispanic-origin name and no "
     "class ever reads like a 2020s roster. Patch: the 485 first names and 485 surnames in the roster template's "
     "name pool become the most common names of 2015-2025 NFL players (nflverse-data, CC-BY-4.0), rewritten inside "
     "the pool's own 13,238 bytes; the 433 surnames the announcer has recorded keep their slot and their call-out, "
     "the 52 replacements (Diggs, Chubb, Kamara...) and every first name are new, and a 27-byte cave on the "
     "generator announces players with a replacement surname by jersey number instead of a wrong name. Only "
     "franchises created from the copy see it. Unwitnessed in game."),
    ("franchise_practice", "Free Practice inside Franchise",
     "Retail: Practice lives only under Game Modes on the main menu, it picks two random teams, and there is no "
     "way into it from a franchise; the Coach's Desk lists Schedule through Quit and its eleven rows end right "
     "where the descriptor begins, so there is no spare slot. Patch: the desk's 52-byte event-hook list is copied "
     "into a cave, which frees exactly one 0x34 row slot, and a Practice row is written there (first, above "
     "Schedule) opening a clone of the Scrimmage Settings screen. The clone's enter hook runs the retail practice "
     "defaults, then puts the team you coach on BOTH sides at Practice Type = Full Scrimmage, so you get your "
     "first-team offence against your first-team defence in your away kit against your home kit on the practice "
     "field, with the live franchise roster (there is only one roster in memory and the franchise load already "
     "overwrote it). Its START handler pops once instead of twice, so a rep ends back on the Coach's Desk. "
     "Practice is game mode 1 and the stat, clock and injury paths are gated on mode 4 and up, so a session "
     "writes no season stats and no injuries; no retail instruction byte is changed. Unwitnessed in game."),
    ("seven_on_seven", "7-on-7 practice mode",
     "Retail Practice offers Special Move, Full Scrimmage, Offense Only and Kickoff. Patch: Practice -> Scrimmage -> "
     "Practice Type gains 7-On-7, which plays as Full Scrimmage with the practice playbook loaded for both teams and "
     "the pass rush off; the practice book gains three 7-on-7 passing sets (Trips, Spread, Ace: QB, a centre to snap, "
     "five skill players) with nine pass concepts and two coverage sets (4-3 and Nickel looks) with six coverages. The "
     "engine always fields eleven, so the four linemen of each side stand idle at the sideline by design, and one "
     "parked defender rushes after a 4-second count as the throw timer. Needs a disc image; unwitnessed in game."),
    ("player_star", "Star decal under the players you tag",
     "Retail already draws a star at a player's feet and the art is called icon_controller_star: it is a "
     "world-space decal the game puts under whoever a controller is driving, and one 80-byte routine decides "
     "who gets one. Patch: that routine is rewritten in place (same 80 bytes, same entry, no cave) so it keeps "
     "every retail answer and also says yes when the player's roster record carries the studio's star bit, "
     "refusing once the game's 9-entry star list is full. Tick the players in Text & Rosters (★ Star); with no "
     "player ticked nothing changes on screen. The same routine gates the on-field name/number indicator, so a "
     "tagged player gets that too when Player Indicator Text is on. The tags need a disc image and reach "
     "franchises created from the copy. Unwitnessed in game."),
    ("depth_roles", "X / Z / SLOT receivers and nickel / dime corners (disc images only)",
     "Retail playbooks have no slot receiver: the inside man of a three-wide set is the #1 receiver in 196 formations, "
     "the #2 in 115, the #3 in 100. Patch: every personnel group is rewritten so the innermost receiver is the third "
     "receiver on your depth chart (SLOT) with X and Z outside, and nickel / dime sets use your third and fourth "
     "corners inside (retail already did for 66 of 71 and 36 of 38 sets). Twelve shared groups whose formations "
     "disagree by more than two yards, bunch sets and special teams keep their retail assignments and are listed in "
     "the build report. Changes who lines up, not how they play: Advanced. No new depth-chart rows yet. Unwitnessed in game."),
    ("depth_chart_rows", "SLOT, NICKEL and DIME rows on the depth chart, X / Z labels (disc images only, experimental)",
     "Retail: the depth chart lists two receivers (LWR / RWR) and two corners; who plays the slot or the nickel is whoever "
     "the formation happens to pick. Patch: the offence gets a SLOT row and both defences get NICKEL CORNER and DIME CORNER "
     "rows (thirteen rows per unit instead of eleven; LWR / RWR become X / Z). The new rows are views onto your receiver "
     "and corner lists, so moving a player there moves him in that list. Needs the one-pool positions and the X / Z / SLOT "
     "playbook roles and switches them on when the disc lacks them. Special teams keep KR, PR, K and P. Unwitnessed in game."),
    ("practice_squad", "Practice squads: 53 active + up to 12 reserves in franchise (experimental)",
     "Retail: the season gate cuts every franchise roster to 53 and the rest become free agents. Patch: each team keeps up to "
     "twelve of the players it cuts as team-owned reserves (the same 65-slot roster table; three spare bytes mark the list). "
     "Reserves stay off the active roster, the depth chart and the team rating, cost no cap space, keep their contract terms, "
     "and survive saves, team imports and the season rollover. There is no in-game reserve screen or automatic promotion yet; "
     "a full 53 + 12 roster must release players to draft. Only use saves with reserves on a disc that carries this patch. "
     "Unwitnessed in game."),
)


class _Signals(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, operation: Callable[[Callable[[str, int, int], None]], object]) -> None:
        super().__init__()
        self.signals = _Signals()
        self._operation = operation
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self._operation(lambda msg, _a, _b: self.signals.progress.emit(msg))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


if not mod_build.SEVEN_ON_SEVEN_RELEASED:
    PATCHES = tuple(entry for entry in PATCHES if entry[0] != "seven_on_seven")

# What each toggle is called on screen (the same words as the Build tab), a one-line helper, and
# the qualifier badge that must stay visible outside Details (E4 / M12).
LABELS: dict[str, tuple[str, str, str]] = {
    "catch_slider": ("Fix Catching & Interception sliders", "Catching controls drops; Interception controls picks.", ""),
    "accel_ramp": ("Gradual player acceleration", "Agility controls how quickly players reach top speed.", ""),
    "draft_ai": ("Smarter Franchise drafts & free agency", "Changes CPU decisions; Fantasy Draft is separate.", ""),
    "returner_fix": ("Fix CPU kick & punt returners", "Changes automatic depth-chart selection.", ""),
    "progression": ("Change player growth & decline", "Growth over years 1-5, harder decline after years 9-12; more stars and busts.", ""),
    "team_column": ("Show TEAM in Player Card season stats", "Which team each season was played for.", ""),
    "kick_rules": ("Modern kick spots & kicking power", "Kickoff: 35 · touchback: 35 · PAT snap: 15.", ""),
    "dynamic_kickoff": ("Dynamic kickoff rule (2024/2025)", "Nobody moves until the ball comes down; landing zone; the CPU kicks to it. "
                        "Switches on the modern kick spots and the alignment.", NOT_TESTED),
    "overtime": ("Modern overtime rules", "Both teams get a possession; regular-season ties remain.", ""),
    "camera": ("Make Standard camera look like Far", "The Standard preset takes Far's look-at, lens and offset.", ""),
    "position_row": ("Change position in Edit Player", "In-game: use Depth Chart → Auto afterward.", NOT_TESTED),
    "probowl_order": ("Pro Bowl Votes: offense, defense, kickers", "The tabs run offence, defence, then K and P.", NOT_TESTED),
    "penalties": ("Adjusted penalty rates (experimental)", "Estimated rates; includes the Chop Block toggle fix.", NOT_TESTED),
    "uniform_choice": ("Choose home/away jerseys at any stadium", "Up/down past the last era flips that side's colour.", NOT_TESTED),
    "kick_laces": ("Laces face the posts on kicks", "On field goals and PATs the held ball is turned so the laces face the posts.", NOT_TESTED),
    "prospect_names": ("Modern draft-prospect names", "New franchises only; some new surnames are announced by number.", "New franchises only"),
    "franchise_practice": ("Free Practice inside Franchise", "A Practice row on the Coach's Desk: your first team against itself.", NOT_TESTED),
    "seven_on_seven": ("7-on-7 practice", "Practice Type 7-On-7 with 7-on-7 sets in the practice playbook.", NOT_TESTED),
    "player_star": ("Show a star under selected players", "Select players under Names, Numbers & Faces; at most 9 stars at once.", NOT_TESTED),
    "depth_roles": ("X / Z / SLOT receivers and nickel / dime corners", "Changes who lines up in every playbook, not how they play.", NOT_TESTED),
    "depth_chart_rows": ("SLOT, NICKEL and DIME rows on the depth chart",
                         "Switches on the merged position groups and the playbook roles when the disc lacks them.", NOT_TESTED),
    "edge_rename": ("Call defensive ends EDGE", "Rosters, depth charts, the draft, the formation editor and the scorebug legend say EDGE.", ""),
    "scheme_labels": ("Use scheme-specific depth-chart names", "4-3: SAM, MIKE, WILL; 3-4: EDGE, MIKE, WILL, NT.", ""),
}

# BuildPlan fields that are profile names rather than booleans: the value a ticked box writes
STRING_TOGGLES = {"penalties": "nfl", "prospect_names": "modern", "uniform_choice": "choice"}
# toggles whose other half lives in pack 0: a bare default.xbe cannot take them
NEEDS_IMAGE = {"prospect_names", "depth_roles", "dynamic_kickoff", "depth_chart_rows"}

TEXT_PATCHES = (
    ("edge_rename", "Rename DE to EDGE everywhere",
     "Retail calls the position DE / Defensive End in rosters, depth charts, the draft, the formation "
     "editor and the scorebug legend. Patch: every one of those strings reads EDGE (the executable's six "
     "position tables plus the disc's own text spans), so the game speaks modern NFL. Formation slots "
     "LDE/RDE show EDGE; abbreviation fields keep four letters."),
    ("scheme_labels", "Depth-chart positions by scheme (MIKE / SAM / WILL, EDGE, NT)",
     "Retail labels every linebacker slot ILB / ROLB / LOLB and every 3-4 lineman DT / DE. Patch: the 4-3 depth "
     "chart reads SAM, MIKE, WILL; the 3-4 chart reads EDGE for the outside backers, MIKE and WILL inside, NT in "
     "the middle. Labels only (each scheme has its own slot records); who fills a slot is unchanged."),
)


# BuildPlan fields that are strings: the value a ticked box writes


class GameplayPatchesPanel(QWidget):
    """A page of executable/text toggles written through mod_build.

    ``patches`` chooses which toggles the page shows (``PATCHES`` for gameplay, ``TEXT_PATCHES`` for
    the EDGE rename); each key must be a BuildPlan field and an ``inspect`` state key.
    """

    def __init__(self, facade: object | None = None, parent: QWidget | None = None, *,
                 patches: tuple[tuple[str, str, str], ...] = PATCHES,
                 title: str = "Game Fixes",
                 intro: str = "Select fixes and write one copy. For presets and other changes, use ★ Build & Share.",
                 target_suffix: str = "gameplay patched") -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._task: _Task | None = None
        self._state: dict[str, object] | None = None
        self.checks: dict[str, QCheckBox] = {}
        self._patches = tuple(patches)
        self._title = title
        self._intro = intro
        self._target_suffix = target_suffix
        self._reading = False
        self._target_generated = False
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------- the open-disc hook
    def begin_reading(self, source: Path | str) -> None:
        self._reading = True
        self.source_field.setText(str(source))
        self.source_status.setText("Reading disc…")
        self._refresh()

    def reading_failed(self, message: str) -> None:
        self._reading = False
        self.source_status.setText(plain_failure("read this disc", message))
        self._refresh()

    def suggest_target(self) -> None:
        source = self.source_field.text().strip()
        if not source or not tt.is_disc_image(source):
            return
        if self.target_field.text().strip() and not self._target_generated:
            return
        self.target_field.setText(suggest_copy_name(source, suffix=self._target_suffix))
        self._target_generated = True

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)
        title = QLabel(self._title)
        title.setObjectName("throwTitle")
        root.addWidget(title)
        intro = QLabel(self._intro + " The source is never changed. " + XEMU_LINE)
        intro.setObjectName("throwMuted")
        intro.setWordWrap(True)
        root.addWidget(intro)
        src = QHBoxLayout()
        self.source_caption = QLabel("Game disc (.iso)")
        src.addWidget(self.source_caption)
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setPlaceholderText("Filled in when you open a disc (top right), or choose a disc / default.xbe here")
        src.addWidget(self.source_field, 1)
        self.source_button = QPushButton("Choose…")
        self.source_button.clicked.connect(self._choose_source)
        src.addWidget(self.source_button)
        root.addLayout(src)
        self.source_status = QLabel("Open your game disc (top right), or choose a disc / default.xbe here, to read which changes it already carries.")
        self.source_status.setObjectName("throwMuted")
        self.source_status.setWordWrap(True)
        root.addWidget(self.source_status)
        self.setStyleSheet(
            "QCheckBox { padding: 4px 2px; spacing: 10px; }"
            "QCheckBox::indicator { width: 20px; height: 20px; border: 2px solid #8a94a6; border-radius: 4px; background: #1b1f27; }"
            "QCheckBox::indicator:unchecked:hover { border-color: #c9d1de; }"
            "QCheckBox::indicator:checked { background: #2ecc71; border-color: #2ecc71; "
            "image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png); }"
            "QCheckBox::indicator:disabled { border-color: #4a5060; background: #22262e; }"
            "QCheckBox::indicator:focus { border-color: #6ee7c7; }"
            "QCheckBox:checked { color: #d8ffe6; font-weight: 600; }"
            "QCheckBox:disabled { color: #6b7385; }"
            "QLabel#optionBadge { color: #f3d27a; background: #2a2a1c; border: 1px solid #6a5a2a; border-radius: 6px; padding: 1px 6px; }")
        self.badges: dict[str, QLabel] = {}
        self._static_badges: dict[str, str] = {}
        list_box = QGroupBox("Changes")
        lb = QVBoxLayout(list_box)
        lb.setSpacing(8)
        for key, label, explanation in self._patches:
            short, helper, badge = LABELS.get(key, (label, "", ""))
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 2)
            rl.setSpacing(1)
            head = QHBoxLayout()
            head.setSpacing(8)
            check = QCheckBox(tab_title(short))
            check.setAccessibleDescription(helper or label)
            check.toggled.connect(lambda _c: self._refresh())
            head.addWidget(check)
            badge_label = QLabel(badge)
            badge_label.setObjectName("optionBadge")
            badge_label.setVisible(bool(badge))
            head.addWidget(badge_label)
            head.addStretch(1)
            rl.addLayout(head)
            if helper:
                helper_label = QLabel(helper)
                helper_label.setObjectName("throwMuted")
                helper_label.setWordWrap(True)
                helper_label.setIndent(30)
                rl.addWidget(helper_label)
            more = Details("Details")
            more.add_text(explanation)
            more.setContentsMargins(30, 0, 0, 0)
            rl.addWidget(more)
            lb.addWidget(row)
            self.checks[key] = check
            self.badges[key] = badge_label
            self._static_badges[key] = badge
        root.addWidget(list_box)
        out = QHBoxLayout()
        self.target_caption = QLabel("Save disc copy as")
        out.addWidget(self.target_caption)
        self.target_field = QLineEdit()
        out.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        self.target_button.clicked.connect(self._choose_target)
        out.addWidget(self.target_button)
        self.target_field.textEdited.connect(lambda _t: self._user_target())
        root.addLayout(out)
        actions = QHBoxLayout()
        self.write_button = QPushButton("Make disc with these changes")
        self.write_button.clicked.connect(self._write)
        actions.addWidget(self.write_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        root.addStretch(1)

    def _user_target(self) -> None:
        self._target_generated = False
        self._refresh()

    def apply_state(self, state: dict[str, object]) -> None:
        self._state = state
        self._reading = False
        self.source_field.setText(str(state.get("path", "")))
        is_image = state.get("container") == "xiso"
        source_caption, target_caption = source_captions(is_image)
        self.source_caption.setText(source_caption)
        self.target_caption.setText(target_caption)
        self.write_button.setText(write_caption(is_image))
        for key, _label, _e in self._patches:
            value = str(state.get(key))
            check = self.checks[key]
            needs_image = key in NEEDS_IMAGE and not is_image
            check.setEnabled(value == "retail" and not needs_image)
            check.setChecked(False)
            tip = {"applied": "Already installed on this source.",
                   "foreign": "Not recognised: the bytes at this change's sites are neither retail nor this patch "
                              "(changed by another tool), so it can't be added here.",
                   "partial": "Only one half of this change is on the source (executable or name pool), so it can't be added here.",
                   "retail": ""}.get(value, "Unknown state.")
            # a known non-retail state is the more useful message; an unreadable one (a bare XBE cannot
            # carry a playbook patch, so inspect says n/a) should say what the user needs instead
            full_disc = needs_image and value not in ("applied", "foreign", "partial")
            check.setToolTip("Full disc required (not a bare default.xbe)." if full_disc else tip)
            badge = ("Full disc required" if full_disc else
                     {"applied": "Already installed", "foreign": "Unrecognized source data",
                      "partial": "Unrecognized source data"}.get(value, self._static_badges.get(key, "")))
            self.badges[key].setText(badge)
            self.badges[key].setVisible(bool(badge))
        row_check = self.checks.get("depth_chart_rows")
        if row_check is not None and any(state.get(k) == "foreign" for k in ("position_pools", "scheme_labels", "depth_roles")):
            row_check.setEnabled(False)
            row_check.setToolTip("Not recognised: something these rows depend on (position groups, scheme names or playbook roles) "
                                 "is neither retail nor this patch, so they can't be added here.")
            self.badges["depth_chart_rows"].setText("Unrecognized source data")
            self.badges["depth_chart_rows"].setVisible(True)
        applied = [LABELS.get(k, (k, "", ""))[0] for k, _l, _e in self._patches if state.get(k) == "applied"]
        foreign = [LABELS.get(k, (k, "", ""))[0] for k, _l, _e in self._patches if state.get(k) in ("foreign", "partial")]
        text = ("Already on this source: " + ", ".join(applied) + "." if applied
                else "No recognized changes found; everything listed is original.")
        if foreign:
            text += " Not recognized (changed by another tool): " + ", ".join(foreign) + "."
        self.source_status.setText(text)
        self.source_status.setToolTip("Read: " + "; ".join(f"{k}: {state.get(k)}" for k, _l, _e in self._patches))
        self.suggest_target()
        self._refresh()

    def plan(self) -> mod_build.BuildPlan:
        plan = mod_build.BuildPlan(
            source=self.source_field.text(), target=self.target_field.text(),
            overwrite=Path(self.target_field.text()).exists() if self.target_field.text() else False,
        )
        for key, check in self.checks.items():
            on = check.isChecked()
            setattr(plan, key, (STRING_TOGGLES[key] if on else "") if key in STRING_TOGGLES else on)
        if plan.depth_chart_rows:
            # the rows build on the pools, the scheme labels and the playbook roles: switch on whatever the source lacks
            state = self._state or {}
            plan.position_pools = plan.position_pools or state.get("position_pools") != "applied"
            plan.scheme_labels = plan.scheme_labels or state.get("scheme_labels") != "applied"
            plan.depth_roles = plan.depth_roles or state.get("depth_roles") != "applied"
        return plan

    def _refresh(self) -> None:
        any_on = any(c.isChecked() for c in self.checks.values())
        self.write_button.setEnabled(any_on and bool(self.source_field.text()) and bool(self.target_field.text())
                                     and self._task is None and not self._reading)

    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose your game disc (.iso) or default.xbe", str(Path.home()), SOURCE_FILTER)
        if not chosen:
            return
        try:
            self.apply_state(mod_build.inspect(Path(chosen)))
        except Exception as exc:  # noqa: BLE001
            show_operation_error(self, "read that file", str(exc))

    def _choose_target(self) -> None:
        is_image = bool(self.source_field.text()) and tt.is_disc_image(self.source_field.text())
        chosen, _f = QFileDialog.getSaveFileName(self, "Where should the new disc go?" if is_image else "Save the patched executable as",
                                                 "ESPN NFL 2K5 (gameplay patched).xiso.iso" if is_image else "default_patched.xbe")
        if chosen:
            self.target_field.setText(chosen)
            self._target_generated = False
            self._refresh()

    def _write(self) -> None:
        plan = self.plan()
        if not any(check.isChecked() for check in self.checks.values()):
            return
        is_image = tt.is_disc_image(plan.source)
        chosen = [LABELS.get(key, (label, "", ""))[0] for key, label, _e in self._patches if self.checks[key].isChecked()]
        answer = QMessageBox.question(self, "Make disc with these changes?" if is_image else "Save a patched executable?",
                                      f"Source (unchanged): {plan.source}\n"
                                      + (f"Replace existing copy: {plan.target}" if plan.overwrite
                                         else f"New {'disc' if is_image else 'executable'}: {plan.target}")
                                      + "\n\nChanges: " + ", ".join(chosen)
                                      + "\n\n" + XEMU_LINE,
                                      QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Ok:
            return
        task = _Task(lambda progress: mod_build.build(plan, progress))
        task.signals.progress.connect(self.status_label.setText)
        task.signals.finished.connect(self._done)
        task.signals.failed.connect(self._failed)
        self._task = task
        self._refresh()
        self._pool.start(task)

    def _done(self, receipt: object) -> None:
        self._task = None
        assert isinstance(receipt, dict)
        target = Path(str(receipt.get("target")))
        self.status_label.setText(
            f"Disc ready: {target.name}. Open it in xemu." if tt.is_disc_image(target)
            else f"Patched executable saved: {target.name}.")
        try:
            self.apply_state(mod_build.inspect(Path(str(receipt.get("target")))))
        except Exception:  # noqa: BLE001
            pass
        self._refresh()

    def _failed(self, message: str) -> None:
        self._task = None
        self.status_label.setText(plain_failure("write the copy", message))
        show_operation_error(self, "write the copy", message)
        self._refresh()


__all__ = ["PATCHES", "TEXT_PATCHES", "GameplayPatchesPanel"]
