# nm1 technical handoff: controlled-player surnames

The implementation contract is [nm1_ATLAS_SPEC.md](nm1_ATLAS_SPEC.md). The
coordinator assigned the complete scorebug-style alphabet to the Opus HUD art
job and authorized a private mechanical retail placeholder for technical proof.
No new letter artwork or retail glyph bytes are included in this repository.

## Live behavior and scope

The retail, public v0.6 and unmodified v0.6.1 base matrix covers Name and Number
& Position on offense and defense before the snap and during play, plus a kick
return at each setting. These are one-controller Quick Game observations.

**The base behaves like retail in these checks. Last names are still present.**
The ordinary indicator label is transient. Control assignment, an RB handoff,
or a defender switch resets the selected entity's timer to 2.0 simulation
seconds. After expiry, the label disappears while the player remains controlled.
A normal QB snap does not restart an expired timer. Name draws the last name;
Number & Position draws the jersey number and position. Both follow the same
timing. Pause freezes the timer and changing the option does not reset it.
All three discs loaded Name from the same copied saved settings.

On the observed retail/public returns, the initially controlled returner caught
the ball without a control change. His label expired before the kick and stayed
absent during the return. On base, the second returner caught the ball and
received control, restarting the timer. His name was visible while running and
then expired. This is a control-transfer distinction, not a base-only change.
A player leaving the camera can also hide a label with a positive timer; those
frames were not treated as expiry evidence.

The coordinator subsequently clarified that the retail expiry is the behavior
to replace. The current patch keeps a human-controlled player's last name
visible for the entire control period under both Name and Number & Position.
None remains disabled. CPU-only players receive no name flag, including through
the former special-label branch. A control transfer removes the old entity's
label immediately and gives the new entity one label through the existing
collector and submission path. Native selection timers continue unchanged.

The decision block at 0x7604A..0x760BC reads entity+0x0C and accepts human
controller ports 0..3. It preserves the native disabled-display and non-field
state2/state3 gates. It does not use mode-specific player numbers, team sides
or any expiry timer. The inactive-entity skip, native projection, packet limit
and single collector traversal remain intact. The selector at
0xF9D0A..0xF9D1B sends both enabled settings to record+0x14, the last name.
There is no second text pass or timer mutation.

Native tests exercise all four ports, expired and positive timers, both enabled
settings, None/unknown settings, CPU/null controllers, control transfer and the
old special-label flag. MyCareer normalizes only the exact declared nm1
collector bytes for its existing native-context guard; other changes still fail.
The actual pinned base reports MyCareer applied before and after nm1.

## Static audit

`nm1_audit.py` reads all three discs directly. The indicator predicate,
collector, default initializer, draw, font setup and submission spans are
byte-identical. Timer reset/countdown spans also match. The projection helper
has the same six changed bytes in both mod discs; its calls at 0xFA2A1 and
0xFA31E target the widescreen projection wrapper at 0x4715A.

The option at 0xE5FF90 has values Name=0, Number & Position=1, None=2. Its
initializer at 0x77C84 writes Name on all three discs; saved settings can
override it. Draw function 0xF9D00 uses record+0x14 for Name, formats number and
position for value1, and skips other values. Submission at 0xFA185 requires
packet+0x0C bit0x20. The ordinary collector gate at 0x76053 requires entity+0x44
positive along with role/game/display gates. A separate special-label path can
request labels without that positive timer, so the timer is not the only
possible source of on-field labels. MyCareer listing 0x75D90 as a guard does not
mean a hook is installed there.

Noah's video at 30:02 and 30:06 shows Williams and Elliott near the green
controller ring. At 33:18 Slye appears below the kicker ring with other labels
near the line. These are evidence of surviving name drawing, not proof of each
runtime caller or mode. The controlled-player matrix supplies the behavioral
comparison above.

## Existing glyphs are insufficient

Source: `data/nfl2k5_scorebug_sprite/template.png`, RGBA, 1536 by 512 pixels;
mapping: `data/nfl2k5_scorebug_sprite/layout.json`; compiled atlas: 256 by 512.
The current provenance is b76-s14 broadcast contour work, not the old
`author_default.py` font-based generator. Do not rerun that generator.

The small and label faces contain digits and whole word fragments, including
GOAL, Inch, es, Down, ST, ND, RD, TH and OT. They have no registered standalone
uppercase text letters. The token T in timeout_tab is a complete TIMEOUT panel,
not a letter T. Splitting word tiles might recover some existing letter pixels,
but even the generous union of their token letters lacks `BFJKMPQUVXYZ`.
Segmentation itself has not been validated. The ESPN wordmark is not a name font.
The older scorebug FONT clones retain retail glyphs and cannot supply the missing
authored letters under the brief's existing-glyph constraint.

Source rectangles below are half-open pixel bounds in the 1536 by 512 sheet.
They are source UV regions, not the compiled atlas's repacked UVs.

| Cell | Source rectangle | Native source size |
| --- | --- | --- |
| label_GOAL | [457, 47, 485, 56] | 28 by 9 |
| label_Inch | [100, 300, 124, 309] | 24 by 9 |
| label_es | [136, 300, 148, 309] | 12 by 9 |
| label_Down | [60, 300, 87, 309] | 27 by 9 |
| label_ST | [532, 47, 541, 56] | 9 by 9 |
| label_ND | [545, 47, 556, 56] | 11 by 9 |
| label_RD | [561, 47, 570, 56] | 9 by 9 |
| label_TH | [574, 47, 583, 56] | 9 by 9 |

## Implemented plumbing and handoff

`mod_editor/core/nfl2k5_indicator_names.py` validates the 40-glyph source atlas,
compiles a private native FONT with per-glyph advances and a one-pixel dark
outline, and binds it only for indicator names. Lowercase roster strings use
uppercase glyph aliases while punctuation and spaces retain their metrics.
The global font slots remain intact. Both enabled text settings now display
the persistent last name; None stays disabled.

The private resource fits the existing appended scorebug scene span by storing
the byte-identical decoded scene with native compression. The new FONT follows
inside that same fixed span. All outer and disc offsets remain unchanged.
The Studio build plan's `indicator_names_folder` field selects the art folder.
`tools/b77/nm1_repair.py` uses the same compiler, refuses unknown disc inputs,
and provides write, zero-write replay, full-disc scope and Studio equality
receipts. See the atlas contract for exact texture, metrics and disc layout.

The private PLACEHOLDER is mechanically repacked from the pinned retail
indicator FONT, with no new letter drawing. It must not be shipped. Final Opus
art replaces `atlas.png` and `metrics.json` in the specified authored directory,
sets `placeholder` false, records provenance, and enters the release allowlist.
The original provisional 512x128/14-pixel proposal is superseded by the exact
256x128/11-pixel contract. Opus owns the final visual approval.

The baseline matrix and persistent-name live checks are complete. A cold boot
of the repaired base copy with the private placeholder FONT showed expired-timer
last names on offense before and after the snap, moving defense and a kick
return under both enabled settings. Defensive control switches replaced the
old label with one new label, including a second switch before the old timer
expired. Normal scrimmage defense also showed the name before and after the
snap. The live checks used one human controller; all four human slots and
CPU rejection are native-code tested, rather than four-pad live tested.

The focused indicator, build and MyCareer suites passed 45 tests. Fixed-span
repair receipts record a zero-write replay, zero changed bytes outside the
declared spans, and equality with the Studio writer. Final Opus art and visual
approval remain separate from this technical proof. The retail-derived
placeholder must not ship.
