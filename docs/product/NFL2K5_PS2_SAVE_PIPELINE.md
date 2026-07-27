# PS2 save support for ESPN NFL 2K5

**What's new: the editor can now write PlayStation 2 memory card saves.**

Point it at a 2K5 PS2 save — straight off a memory card image, or a save file
you've already pulled out — change a player's name, and it writes you a new
save file you can load in PCSX2. Your original save is never touched; you get
a fresh copy.

## Why we could do this on PS2 but not on Xbox

This is the interesting part.

On the Xbox version, every save is signed with a key that lives inside the
console. Change one byte and the game rejects it. That's why save editing has
been off the table on the Xbox side — it isn't a matter of effort, the door is
locked.

**The PS2 version doesn't do that.** It protects saves with a simple checksum
— the same kind of thing a ZIP file uses. Anyone can recalculate it. So we can
edit a save, redo the checksum, and the game is happy.

We confirmed this two separate ways: we checked five real saves off a memory
card (roster, franchise, playbook, VIP) and the checksum matched every time,
and we also found the checksum code sitting right there inside the game's own
program file. Same answer from both directions.

The other lucky break: the PS2 roster save uses the **same roster format as the
game disc**. The tools in this project already knew how to read that. When we
pointed them at a PS2 save they read it perfectly — all 2,479 players, 52
teams, the colleges, the coaches. Nothing new to figure out.

## How we keep it safe

- Edits have to **fit in the space the old text used**. If a name is too long,
  the editor refuses instead of quietly breaking something.
- A **separate checking program** looks at the before and after files and
  proves only the bytes we meant to change actually changed, that the checksum
  is right, and that the roster tables are all still where they belong. It
  doesn't take the editor's word for it.
- Your source save is read-only. Output goes to a new file.

We've run this end to end on a real save: renamed a player, resealed it,
wrote it out, read it back, and the checker passed.

**One honest note:** we haven't yet sat down and watched the game load one of
these edited saves. Everything checks out on the file side, but that last step
is still to come — see below.

## We've already done this for Madden and NCAA

This isn't our first PS2 save project, and that's the real reason to be
excited about where it goes.

We already built a full pipeline for **Madden 08, 09 and 12 on PS2**. It works
like this: the game itself never gets modified. Instead we build the *content*
— rosters, draft classes, franchise files — and deliver them as memory card
saves. Load them up and you're playing with them.

What's in it today:

- Real NFL data for **every season from 2008 through 2026**, pulled from
  proper sources, not hand-typed.
- Draft classes and opening-day rosters generated for each of those years.
- Franchise files with the correct year, the correct salary cap, real player
  contracts (spot-checked against actual figures — Rodgers, Brady, Garoppolo
  all landed on the dollar), and real career stats.
- All of it **tested in PCSX2**, not just theorized. We loaded them and
  checked the game showed the right year, the right cap, the right numbers.
- Plus the tooling to package it all onto a memory card.

The only piece that doesn't carry straight over to 2K5 is the file format
itself — Madden and 2K5 store rosters differently. That's exactly the gap the
new code in this update fills. Everything above it, we already have.

## The bigger idea: the progression engine

Here's what we're really building toward.

A 2004 football game can't grow old gracefully. Its rosters, its salary cap,
its contract logic, its draft classes are all frozen in 2004. Sim forward and
you get a decade of made-up players and made-up outcomes.

So instead we do the aging ourselves, outside the game. We call it a **custom
progression engine**: it sets the year, rebuilds the salary cap to match that
season, works out every player's contract, fills in real career stats, and
seeds the draft with the actual prospects from that year. Then it writes all
of that into a save.

The payoff: **pick any season and play it.** Not "start in 2004 and sim
twenty years" — actually start in 2015, or 2021, with the real rosters, real
contracts and real numbers for that year.

That already works for Madden. For 2K5 we've now found where the pieces live —
the gameplay sliders, the player ratings, the franchise data — so the same
engine shape fits. This update is the first working piece of it: the ability
to write a save the game will accept.

## What's next

1. **Watch it load.** The quickest proof is the VIP save — it stores the
   custom ESPN ticker text you can set in-game. Edit that, boot it up, and if
   your text scrolls across the bottom, we've proven the whole chain works.
2. **Move from names to ratings.** We know where the ratings live; we just
   want to label each one properly before touching them.
3. **Build the roster generator**, so any year from our database can be turned
   into a 2K5 save on demand — the same thing the Madden side does now.

## Where this work is happening

All of this comes out of the ongoing work in our **Discord** — genuinely
cutting-edge stuff that hasn't been done before on these games: cracking the
save formats, digging through the PS2 code, generating whole seasons of real
football data and getting it running on twenty-year-old hardware. The
experiments, findings and early builds land there first, and this update is
one of them.
