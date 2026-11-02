# Rosters > Coaches: the coaching staff plan

The **Coaches** tab of the Rosters page plans staff changes for a build. Open a game disc (top right, or **Open disc
roster** on the Roster tab) and the tab lists the 32 clubs with their head coach, read from that disc's own roster, and
their 2026 defensive coordinator from the Studio's data. You can:

* **Swap head coaches**: two clubs exchange head coaches, nobody loses a job.
* **Hire a head coach**: pick a head coach from another club (the two clubs swap), or pick a coach who was let go earlier
  in the plan, or **Create a new coach** (name, three biography lines, the game's sideline model, whose play calling he
  borrows, an overall rating). The coach he replaces is let go and leaves the roster.
* **Change coordinator**: a club takes another club's defensive coordinator; the two defenses swap.
* **He brings his old club's playbook**: a coach who arrives at a club can bring his old club's playbook instead of the
  club keeping its own. His play calling style always moves with him.
* **Put every coach back**, **Save staff file**, **Load staff file**: reset, or keep a plan as a small file (a "what if"
  staff) to load or share later. A loaded file is checked against the roster first and refused, with the reason, when
  it does not fit.

Every change joins the Rosters page's Undo and Redo (the toolbar above the tabs) and counts as a roster edit. The page
never writes your disc. **Export roster edits** adds the plan as the `staff` section of the roster-edits file, and
Build applies it when it makes the disc.

## The document

```json
"staff": {
  "schema": "nfl2k5_coach_staff/v1",
  "head_coaches": [{"team": "OAK", "coach": "Andy Reid"},
                   {"team": "NYG", "created": "pat-shurmur", "playbook": "coach"}],
  "defensive_coordinators": [{"team": "DAL", "dc": "PHI"}],
  "created_coaches": [{"id": "pat-shurmur", "first": "Pat", "last": "Shurmur", "bio": ["", "", ""], "body": 50,
                       "photo": 8999, "style": "SF", "ratings": {"overall": 70}}]
}
```

`team` is the club's book code (SF CHI CIN ... ARZ SD ... OAK STL WAS), `coach` a head coach's full name on the loaded
roster, `dc` the book code of the club a 2026 coordinator comes from, `playbook` is written only as `coach` (he brings
his playbook); without it the club keeps its own. Clubs not listed keep their coach. One head coach and one coordinator
per club, nobody in two seats, nobody lost without being replaced, coaches told apart by name (a new coach cannot take
the name of a head coach in the plan, and a new coach brings a playbook only when he calls plays like another coach):
`mod_editor/core/nfl2k5_staff_ui.py` builds every document with those rules and `problems()` says in plain words what is
wrong with one that was written by hand. This is the form `nfl2k5_coach_staff.normalize` returns, apart from empty
`tendencies` and `fields` it adds to a new coach.

The build-time writer is `nfl2k5_coach_staff` (b780 job c2-staff). When that module is in the Studio, the page asks it
about the plan a moment after the last change (one question per burst of changes, only while the page is shown) and shows
what it says: its notes and problems, and for the selected club where his playbook comes from and whether the automatic
2026 play calling binds to the new coach and why not. The exported section is the engine's own canonical form. Until
the module is there the page says so, and a build ignores the section.

```
python3 -m mod_editor.core.nfl2k5_staff_ui                         # the 32 clubs and their coordinators
python3 -m mod_editor.core.nfl2k5_staff_ui STAFF.json --disc GAME.iso   # check a staff file against a disc
```

## Franchise saves

A franchise save is not planned on this tab: the Franchise page has its own Coaches tab with **Swap with another
club**, **Fire and hire** and **Hire for a club** (see `franchise_save.md`, "Head coach moves").

## Proof level

EXPERIMENTAL / UNWITNESSED. Offline: the staff functions and the page run against synthetic rosters and the released
SOFTDRINK v0.8 disc's own roster (read only); the save moves run against a synthetic arena and the Franchise1 and Finn
fixtures, with signed round trips. Nobody has built a disc from a staff plan or played a moved coach in the game yet.
