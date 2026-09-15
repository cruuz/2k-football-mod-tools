# Beta 70: the 2026 Monday Night Football scorebug and the Berman freeze (Claude Fable 5.1, 2026-09-15)

EXPERIMENTAL. Seen by Claude in the xemu emulator (section 6); not yet witnessed by a player on hardware. This
report is the evidence trail for the rebuilt runtime scorebug option ("ESPN Monday Night Football 2026 scorebug
(experimental)", `scorebug_runtime`, off in every preset) and for the root cause of the freeze after Berman's
intro that testers reported on beta 69.

## 1. The freeze, reproduced and root-caused

- Reporters: andrethealchemist (2026-09-14 11:35 PM, #2k5-general): "selecting the "scorebug effects" option
  in the mod editor is known to freeze the game after Berman's intro, but if you go into situation mode instead
  of play now/franchise, (bypassing Berman) you can see how cool the scorebug effects looks in game."
  TheWildJeffrey (beta 68): "freezing right after Berman and repeating audio".
- Reproduction (2026-09-15 04:41, xemu in a nested display, gdb stub attached, quick-game route with the intro
  on, disc = retail + beta 69 `scorebug=True, scorebug_runtime=True`): the game halts inside the first minute of
  the intro. The guest CPU sits in the kernel bugcheck loop at 0x800151EF with code 0x1E
  (KMODE_EXCEPTION_NOT_HANDLED), exception 0xC0000005 at kernel EIP 0x8001DBD4, a WRITE to address 0. That
  instruction is `rep movsd` in the kernel's partial-page file read copy (the FSC path under NtReadFile).
  The game-side request came from the resource loader (`0x4D630` state machine, `0x4AF70` read step,
  `0x1D8D2` NtReadFile wrapper); the loader's busy flag `0xB09584` was 1. The read request record carries its
  destination buffer at +0x1C (`0x4BBAB` writes it into `0xA7D364`) and nothing checks that pointer for null.
- Discriminator (2026-09-15 04:58, same route, same two hooks, only the appended resource volume changed):
  the beta 69 build appends 264 panel textures and 7 private fonts (1.7 MB) to the HUD collection; a build with
  8 textures and the fonts (0.4 MB) reaches the coin toss and the kickoff with the runtime bar drawn (screens in
  `/media/noah/Storage/.b70-probe/run2/screens/`). Same hooks, same binding code, so the appended volume during the
  intro's peak is what makes a later allocation fail and the read go to null.
- Fix in beta 70: the option appends 66 textures (0.35 MB) and no private fonts (the size class that passed).
  The loader's missing null check is retail code and is not patched.
- A second stop, found on the way: with the intro passed, the first 2026 build stood still at the coin toss
  (run 5, 06:00). The plate-tint code read the team context through `[0xE60280]+0x10c` while that pointer
  still named another structure. The owner now resolves the possessing side by comparing the possession word
  with the two team objects and the two score pointers, and reads the asset code from the validated team
  context only; an unexpected word tints nothing. Run 6 went through the toss.

## 2. What the 2026 bar is (measured from the Chiefs at Broncos capture, 1920x1080, 30,044 frames)

Bar rails x 437..1478, y 942..1052 (54% of the frame wide, 10% tall); wings with the team logo on the team
colour fading into charcoal; big white scores; three timeout dashes under each score; the down plate
x 830..1090, y 946..988 in the possessing team's colour; the white clock capsule x 838..1082, y 998..1044
with the quarter as small caps, the game clock, and the play clock (dark, ESPN red in the last seconds);
the ESPN wordmark in the plate on dead balls and kickoffs; "2nd Down" between plays; the TOUCHDOWN slab.
Mapped to the 640x448 HUD with the same transform the static v3 bar uses (`nfl2k5_scorebug_exact.MNF_*`).

## 3. What beta 70 builds (all offline-proved, unwitnessed)

- Scene: `exact.mesh_mnf` re-lays the retail `score_bug` SCNE into the 2026 geometry (fixed 4,800-byte span,
  4,789 used, wrapper identical); atlas `exact.atlas_mnf` (64x64 P8, 22 colours, fixed span).
- Wings: 66 native 128x32 TXTRs (`sb<code><side>0`), one per team side plus neutral, the current logos from
  `data/nfl2k5_scorebug_mnf/logos/` on the team colour (`exact.mnf_panel`), appended to outer 346.
- Owner (`nfl2k5_scorebug_runtime`, revision 6, 1,389 of 1,408 bytes): binds one texture per side at setup,
  looks up the down plate material by name, installs two dash callbacks into the retail team-name records,
  and per frame keeps the wings bound, flashes a changed score, re-fires the native slide on a new down, tints
  the plate from a 40-entry colour table indexed by the possessing team's asset code, and colours the play clock.
- Fonts: `nfl2k5_scorebug_mnf_font` can paint ESPN digit shapes (sampled from the broadcast) into the retail
  FONT4 and FONT8 glyph cells in their fixed spans with the metrics untouched. It is HELD BACK: two emulator
  runs with the restyled fonts stalled in the intro movie (the loader request stayed pending), so the build
  ships the retail fonts unless `NFL2K5_MNF_FONTS=1` is set in the environment of the build. The digits on the
  bar are therefore the retail glyphs in this beta.
- Text records: the two team-name records become the timeout dashes (FONT8, centred, white), the capsule text
  is dark, the plate text white, the literal "Goal" becomes "GOAL", and the two game-clock records are centred
  (retail right-aligns them).
- Clock capsule cells (after run 6): the retail HUD glyphs are wider than ESPN's, so the capsule's two
  separators sit at 24/64 and 50/64 of the tile and the quarter (source x 883), the game clock (978, centred)
  and the play clock (1055) each sit in their own cell; "1ST", a two-digit clock such as "13:10" and the play
  clock no longer touch (the native renderer shows the same layout the emulator showed in run 6).

## 4. Not built yet

The ESPN wordmark dead-ball state, "2nd Down" between plays, the TOUCHDOWN slab, letters beyond digits in the
fonts, and the tenth font slot route (a third Fable line researched asset replacement in parallel; see
`FABLE_B70_ASSETS_REPORT_2026-09-15.md` when present).

## 5. Seen in the emulator (run 6, 2026-09-15 06:09 to 06:17)

Disc: retail + `scorebug=1, scorebug_runtime=1` from this worktree (`/media/noah/Storage/.b70-probe/mnf4.xiso.iso`),
xemu in a nested display with the virtual pad pressing START/A blindly (`docs/scorebug_mnf/witness/run6_cmds.txt`).
The game went through the Berman intro, the coin toss and the kickoff play call into live play (Lions at Giants)
with the 2026 bar drawn: team-colour wings with the current logos, white scores, the possession-tinted down
plate ("4th & Inches" on Lions blue), the white clock capsule, and three timeout dashes each side. Frames
`docs/scorebug_mnf/witness/run6_toss.jpg`, `run6_kick.jpg`, `run6_play4_live_play.jpg`; bar crop
`run6_play4_bar.png`; the debugger capture at +470 s (`run6_gdb_registers.txt`) shows the CPU in game code
(EIP 0x248F0), not the bugcheck loop. One flaw seen there, the "1" of "1ST" outside the capsule cell, is what
the capsule re-spacing above corrects; that correction is proved by the native renderer only.

## 6. Witness list for Noah

Play Now with the intro on, then Franchise: the game must reach the kickoff; the bar sits at the bottom centre
with both logos, the plate colour follows the ball, a used timeout drops a dash, the play clock turns red under
five seconds, the scores flash on a change. Report anything that looks off with a photo.
