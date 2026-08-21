# APF Field Art — stock NFL vs focused editor (wall + path)

## User report

Field art appears for created-team workflows, but stock NFL endzone / field
assets seem missing from the dedicated Field Art editor even though they show
under All Textures.

## What is true in product code

1. **Inventory (browse/export):** `build_field_art_inventory` exposes **258**
   Field Art rows including **≈118 endzone_l0** and **117 endzone_l1** package
   pairs (stock NFL package-local art). These appear in the Field Art inventory
   browser and All Textures under the field-art category filter.
2. **Focused editor (writable):** `FIELD_ART_COVERED_TARGETS` offers the
   original six bases plus descriptor-derived extras the writer can prove:
   21 package-659 weave/dirtmaps and 194 additional format-18 endzones
   (221 slots total). Thirty-nine format-59 DXT5A `endzone_l1` layers stay
   browse/export-only. That split is intentional honesty, not a missing
   catalog filter bug.
3. **Created teams:** custom-team appearance / user slots may surface different
   authoring paths; stock endzones remain package-local TXTR pairs until a
   per-package writer is proved.

## Correction (2026-08-13): outer 6 is not a shared layer

This document and the Field Art category blurb both described outer 6 as a
**shared** endzone layer. That is wrong, and it mattered: it told users that
editing outer 6 changed a common layer when it actually repaints one specific
team's endzone.

Reported by davidhbui against Beta 38 and confirmed here by decoding the
retail volume:

- Outer 6 `endzone_l0` is bespoke per-team artwork — two figures in
  wide-brimmed hats with bandoliers and revolvers, a masked figure, and a
  hitching rail. A Bandits/Gunslingers-class design.
- It is structurally identical to the other 117 packages: 2048×512, Xenos
  format 18 (DXT1), the same two-layer `endzone_l0` / `endzone_l1` split.
- Nothing distinguishes it except that it is the package whose writer was
  proved first.

Outer 6 is therefore **one team's endzone that happens to be writable**, and
the copy now says so.

### These are region masks, not artwork

Decoding any endzone gives pure red / green / blue region selectors over black
with uniformly opaque alpha — the same contract as `jersey_color` and
`shoulder_color`. The visible colours are shader-driven. A user who exports one
expecting to repaint "the endzone art" gets a three-colour mask, and any future
writer inherits the uniform authoring rules: hard edges, flat colours, no
anti-aliasing, because intermediate values are invalid region IDs rather than
blends.

Endzone alpha is uniformly 255, so the Beta 36/37 zero-alpha display rule
correctly does not fire here. No action needed there.

### Finding a per-team endzone

Endzone rows carry no team identity, and the nickname is not on the disc:
`Redcoats` appears zero times in `0A`, `0B`, `1A`, `1B`, and `default.xex`
across ASCII, UTF-16BE and UTF-16LE — it exists only in `Roster.ROS`. Of 65
nicknames davidhbui sampled, exactly one (`Owls`) produces any byte match in
`0A`, and a four-byte common word matching once in a 1.1 GB binary is not
evidence of a name string. Text search cannot work, by construction.

The supported discovery path is therefore visual: **Export endzone contact
sheet…** in the Field Art panel renders every `endzone_l0` base level into
labelled grids so a package can be identified by eye in one action instead of
an afternoon of scripting. `mod_editor/data/apf2k8_endzone_labels.v1.json`
carries the identifications made so far, each with the person who made it; the
panel labels those rows and leaves the rest as indices rather than guessing.

## Unblock path

1. Pin one stock team endzone package (outer index + l0/l1) with retail SHA pins.
2. Extend `apf_field_art_patch` (or a sibling) to that package with independent
   volume verifier.
3. Expand `FIELD_ART_COVERED_TARGETS` only after the gate is green.
4. Grow the label table from contact sheets as identifications are confirmed.

## Status

Wall documented 2026-08-07. Focused panel copy now states stock endzones live
in the inventory browser; no overclaim of per-team Editable endzone writes.

**UI (2026-08-08):** Field Art ownership map includes a **Stock NFL endzones**
button that selects the endzone semantic family (≈235 TXTR rows / 118 packages)
without Discord help. Still browse/export-only.

**Correction + discovery (2026-08-13):** the "shared" claim is withdrawn above;
contact-sheet export and the label table ship in its place. Still
browse/export-only.
