# Community playbook packs (`.2k5book`)

The stock playbooks are the weakest part of ESPN NFL 2K5 today. Measured across
all 32 team books: shotgun is 18 % of offensive formations and only **14.5 % of
the plays you can actually call**; **six books (ATL, DEN, NYJ, PHI, SF, TB) have
exactly one gun formation and in all six it is "Hail Mary"**; there are zero
pistol sets; 25 of 32 books have exactly one five-wide formation; and 38.7 % of
all route stems are exactly ten yards.

A **playbook pack** is how the community fixes that together. It is a small JSON
file — a *recipe*, not a book — that says "put this formation here, this play
there, and here is what each one replaces". You author it in the studio you
already have, and anyone with their own legal copy of the game can install it.

---

## What a pack is, and what it is not

A pack is the studio's own staged edits written out as JSON: the same
`formation_creates` / `play_creates` / `formation_links` rows a `.2k5mod`
project already stores and the same rows the writer already compiles. That means:

* **Zero retail bytes.** Every entry is an index, a name you typed, eleven
  coordinates you dragged, and node chains built from the game's own opcode
  grammar. No part of anybody's disc travels with the file. (The one digest it
  carries, `base.book_fingerprint`, is a SHA-256 of the book you started from —
  a fingerprint, not data.)
* **Reviewable and mergeable.** It is text. You can read a diff of it, comment on
  a line of it, and merge two people's work.
* **Portable.** The pack names the team it was authored on, and the studio can
  retarget it to any other team by re-resolving each target *by name* in that
  team's own book. 29 of the 32 books order their skill players differently from
  ATL, so a retarget also re-slots every chain onto the player it was drawn for
  and renumbers every operand that names a slot (a handoff still points at the
  back who takes it).

It is not a `.2k5patch` (opaque byte runs, unmergeable — that stays the *end*
product, what you share after Build) and it is not a raw 78,768-byte book blob
(structurally trivial, but 90 % somebody else's game data).

## The one constraint that shapes everything: capacity

| resource | cap | spare per team book (min / mean / max) |
|---|---|---|
| plays | **270** | **0** / 5.6 / 21 |
| formations | 50 | 1 / 7.5 / 11 |
| nodes | 3,500 | 761 / 877 / 1,105 |
| links per formation | 36 | max 33 used |
| nodes per chain | 15 | retail max 7 |
| custom name | 40 printable ASCII characters | — |

**Eight books are already at the 270-play cap** (ARZ, BUF, CIN, HOU, JAX, NYJ,
OAK, SD) and there are only 180 spare play slots across all 32 books combined.
So a pack meant to fit everywhere must **replace, never append**. The check
reports net growth on every run; a pack with net-zero growth installs into all
32 books, a pack that adds plays will not.

There is a trick that makes net-zero easy: when a pack **replaces a formation**,
that formation keeps its existing play menu. So if the pack's plays also replace
plays that were already listed in that formation, the new plays land in the new
formation's menu with no new link and no growth at all. That is exactly how the
shipped seed pack is built.

---

## Authoring a pack in the studio

You need the released studio and your own legal copy of the game. No Python, no
git, no retail packs.

1. **File → Open** your NFL 2K5 disc image.
2. Go to **★ Create a Play** (or the **Playbooks & Plays** tab if you prefer the
   raw designers) and build your formations and plays the normal way.
   * Step 2 lays out the formation. The alignment rules are checked live: seven
     on the line, at most four in the backfield, no linemen covering the ends.
   * Step 4 hands out jobs. Every play is run through the ported retail
     validator before it can be staged.
   * Step 5 chooses what each design **replaces**. Prefer a replacement over
     "add as new" — see the capacity table above. The wizard ranks the most
     dated stock candidates for you.
   * Step 5 also carries the two newest controls: the **QB read order** (the four
     ordered 1–5 values every Dropback node carries) and the **audible slot**
     (which of the formation's three audible groups lists the play).
3. Back on **Playbooks & Plays**, pick your book and press
   **Export Playbook Pack…**. Fill in a name, your handle, a version and a
   licence, choose where to save it, done.
4. Post the `.2k5book` in a thread or attach it to a pull request.

## Installing somebody else's pack

**Playbooks & Plays → Install Playbook Pack…** (there is the same card on
Create a Play step 1).

You get a plan table before anything happens: one row per entry, what it
replaces, and whether it is `ok`, `retargeted`, a `conflict` with an edit you
already staged, or `over budget`. Under it is the live budget bar —
`plays 254/270, formations 39/50, nodes 2,746/3,500`. The team combo offers the
pack's own team, a retarget to any other book, or all 32 team books at once.

Installing stages ordinary project edits. They appear in the normal edit list,
they revert one at a time, and they save into your `.2k5mod` like anything else.
Build compiles them against **your** disc.

## Checking a pack from a terminal

```
tools/nfl2k5_playbook_pack.py check PACK.2k5book
tools/nfl2k5_playbook_pack.py check PACK.2k5book --image DISC_OR_PACK_DIR [--team GB]
tools/nfl2k5_playbook_pack.py check PACK.2k5book --image DISC_OR_PACK_DIR --all-teams
tools/nfl2k5_playbook_pack.py retarget PACK.2k5book --team GB --image DISC -o GB.2k5book
tools/nfl2k5_playbook_pack.py export PROJECT.2k5mod -o PACK.2k5book --image DISC
```

The first six checks need **no game data at all**, so a reviewer or a CI job can
run them on the JSON alone:

| # | stage | what it proves |
|---|---|---|
| 1 | schema | the document is a v1 pack and every field has the right type |
| 2 | budget | 50 formations / 270 plays / 3,500 nodes / 36 links / 15-node chains / 40-char names; net growth reported |
| 3 | validator | the ported retail play validator accepts every play, with the descriptors the game itself computes |
| 4 | class flags | `play_flags & 0x1FF` is still the donor's, and the QB chain's shape agrees with the header's class nibble |
| 5 | legality | every formation obeys the NFL alignment rules |
| 6 | donor | the donor is a stock play of the same shape from `reference_play_for`, never "the book's first play" |
| 7 | compile | a real dry compile through the writer — needs `--book` or `--image` |

Check 4 exists because of a real bug: the first wizard pass play was cloned from
the book's first offensive play, which is a *run* in every retail book. A pass
chain under a run-class header is **played as a run** — the receiver icons flash
and vanish at the snap and the quarterback cannot throw.

`check` exits 0 when every stage is green, so it drops straight into a GitHub
Action over a `books/` directory.

---

## What the engine can and cannot do

Be honest in your pack notes. The engine reaches roughly **80 % of a 2015
offence and 50 % of a 2024 one**.

**Yes, and witnessed in retail:** gun spread 10/11 personnel, empty, pistol,
routes out to about 40 yards (the distance operand is an 8-bit foot field that
spans ~63 yards, and a 35-yard stem passes the validator), mesh / levels /
dagger / flood / stick / smash and the rest of the pure-geometry concepts,
read and speed option with a pitch, nickel and dime, Tampa 2, big nickel and
3-3-5 fronts.

**Accepted by the validator but never witnessed in game** — say so if you ship
one:

* **option routes** (the `0x1A` conditional's kind 0 reads what another player is
  doing right now: zone, man, rush lane, route, block, handoff, dropback; it is
  implemented in the shipped executable and used by *zero* retail plays);
* **keep-or-throw RPO** (the quarterback keeps the read and throws).

**No. The engine cannot do these, whatever a pack claims:**

* **No pre-snap motion.** No opcode has a pre-snap phase, and all 88,254 retail
  Start nodes sit at x = 0, y = 0.
* **No give-or-throw RPO.** The ball simulation walks each chain once and in
  order, so once the quarterback hands the ball off he cannot throw later in the
  same chain. A play built that way is rejected with "node 5 needs the ball but
  nobody gave it to slot 0".
* **No tempo / no-huddle.** That is game logic, not play data.
* **Jet sweep is partial** — the pitch and reverse mechanics ship, the pre-snap
  motion does not.

## Sharing, and the test division

A pack is somebody's work. Put your handle in `book.author` and a real licence in
`book.license` (the shipped seed pack is CC0-1.0).

The workflow that catches the most:

1. the author runs `check` green on all six offline rules and posts a Practice-mode
   clip of every authored play;
2. a second contributor plays one half against the CPU and reports stalls,
   mis-assignments or broken menus;
3. anything using the conditional node (option routes, RPOs) or a rebuilt defence
   goes to Noah, because that is where "the validator accepted it" and "it works"
   can diverge.

Acceptance for a pack that wants to ship: the CLI check green on all six rules;
net formation and play counts unchanged for every target book; every authored
play listed in at least one formation menu with no formation over 36 links; a dry
compile that succeeds and re-parses; a Practice clip per play; one clean
CPU-vs-CPU half.

---

## The shipped seed pack

`data/playbooks/modern_gun_core.2k5book` — **Modern Gun Core**, stages 1 and 2 of
the curated plan, authored on **ATL** (one of the six books whose only gun
formation is "Hail Mary").

Four gun sets, each replacing a ranked dated formation, and eleven pass concepts
built from the library's own `PASS_CONCEPTS`, each replacing a play that was
already listed in the formation it takes over — so the book's formation count,
play count and every menu stay exactly where they were.

| set | replaces (on ATL) | plays |
|---|---|---|
| Gun Trips Rt | Split Jokers | Mesh, Levels, Stick |
| Gun Doubles | I Jokers | Dagger, 4 Verts, Curl-Flat |
| Gun Bunch Rt | Strong I Pro | Snag, Smash, Y-Cross |
| Gun Empty | Weak I Jokers | Slant-Flat, Flood |

Net growth: 0 formations, 0 plays; +308 nodes (2,438 → 2,746 of 3,500). It passes
all seven checks on ATL and, retargeted by name, on all 32 team books — including
the eight already at the 270-play cap.

It is **not** in any Build preset. A community book is a user choice like a
commentary swap; a curated official one would go into EXPERIMENTAL first.

## The file format, field by field

```jsonc
{
  "schema": "nfl2k5_playbook_pack/v1",
  "book":   { "team": "ATL", "name": "…", "author": "…", "version": "1.0.0",
              "license": "CC0-1.0",
              "targets": ["ALL"],          // optional; default is just "team"
              "notes": "…" },
  "base":   { "book_fingerprint": "<sha256 of the retail 0x13390 body>",
              "donor_formation_count": 39, "donor_play_count": 254,
              "donor_node_count": 2438,
              "xiso_sha256": "…" },        // optional, pins the disc
  "budget": { "formations": 50, "plays": 270, "nodes": 3500,
              "links_per_formation": 36, "nodes_per_chain": 15, "name_chars": 40 },
  "formations": [{
      "id": "gun-trips-rt", "custom_name": "Gun Trips Rt",
      "donor": { "index": 10, "name": "Ace" },
      "replace_index": 4, "replace_name": "Split Jokers",
      "slot_positions": [[x_cm, depth_cm], …11],
      "position_codes": [ …11 ],           // who lines up in each slot
      "category_index": 4,
      "category_positions": [ …11 ]        // only when no stock group fields the mix
  }],
  "plays": [{
      "id": "gun-trips-rt-mesh", "custom_name": "Gun Trips Rt Mesh",
      "play_type": "pass", "concept": "Mesh",
      "donor": { "index": 88, "name": "RO F Dump", "flags": 25614, "signature": "pass" },
      "play_flags": 25614,
      "replace_index": 160, "replace_name": "Strong Split Sweep",
      "link_formation": "gun-trips-rt",    // a pack formation id, or an existing index
      "link_group": null,                  // 0-3: the three audible slots
      "assignments": [ [[opcode, [operands…]], …], …11 ]   // null keeps the donor's chain
  }]
}
```

Every field on `formations[]` and `plays[]` other than `id`, the `donor` /
`replace_name` provenance and `link_*` is a field of the writer's own
`FormationCreateRequest` / `PlayCreateRequest` request dataclasses, which is why
installing a pack needs no new project schema. The provenance fields exist so the
offline check can run without the disc and so a retarget can re-resolve by name.

`book_fingerprint` is what lets the importer *report* rather than guess: if the
book on your disc does not match the one the pack was authored on (another patch
already touched it, or you are installing on a different team), the studio says
so and re-resolves every target by name instead of trusting the stored index.
