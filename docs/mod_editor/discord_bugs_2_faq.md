# Community fixes, batch 2

These editor changes require the integration described in WIRING.md. Gameplay
results remain experimental and unwitnessed until the listed comparisons are played.

- **Team Kit bundle into another project.** On the current beta, work around
  the "working pixels changed after export for Torso / Jersey" error by
  exporting a fresh Team Kit **from the main project**, for the same team,
  style and sides. Copy your edited PNGs over the matching files in that new
  export, keeping their names and dimensions. Keep the new manifest and guide,
  then import that bundle into the main project. Its baselines now match;
  only the components you edited change. Do not copy untouched PNGs from the
  old bundle over the main project's existing edits.
  The r64 correction is **EXPERIMENTAL / UNWITNESSED** and needs the protected
  UI handoff in WIRING.md. It accepts edited PNGs from another project using
  the same original source. Untouched bundle components preserve the main
  project's edits, including number sheets. Edited components replace that
  slot and report whether they replaced source or your earlier edit. The
  receipt lists imported, skipped unchanged and overwritten components;
  an immediate repeat keeps that receipt and adds no Undo action. Choose the
  matching team, style and sides in Team Kit before import. Horizontal sheets
  and kits can be imported in either order; the last edited PNG for a digit
  wins. Save the replacement-only `.2k5mod` to share; keep working kits private.
- **How do I arrange a 0-9 sheet?** Use equal cells in one row, one column,
  five columns by two rows, or two columns by five rows, and select that layout.
  Read left to right, then top to bottom, starting at 0. See
  [number sheet instructions](number_sheets.md) for dimensions, padding and alpha.
- **Why do some imported numbers look blocky even at 64x64?** The old digit
  encoder rebuilt the smaller textures by choosing a winning colour in each
  group of four pixels. Thin outlines and soft transparency could become thick,
  uneven steps. It could also reduce a difficult sheet to very few colours to
  fit the game's fixed slot. This is reproduced offline; it does not establish
  the exact cause of Coach Edwards's photographed game without his PNG/project.
  The r64 correction is **EXPERIMENTAL / UNWITNESSED**: it averages colour with
  transparency, preserves fractional coverage in smaller textures, shares one
  palette across every level, and refuses excessive colour loss. Making the
  drawing smaller inside its cell does not change that slot or the old filter;
  it gives the digit fewer pixels and can make a thin outline disappear.
  A 64x64 cell alone cannot guarantee quality. Use the exact target shape,
  straight-alpha transparency and a few flat fill/outline colours. Avoid noise,
  tiny outlines and repeated resizing. See the [clean digit recipe](number_sheets.md#clean-digit-recipe).
  After the protected preview dialog is integrated, inspect every digit at small
  size on both light and dark backgrounds before choosing **Import all ten digits**.
  The preview decodes the actual encoded textures. Its camera-size views are
  estimates; verify broadcast and close views in the game.
- **How do I combine APF logos and endzones?** Load the original game folder,
  stage every supported texture in one project, save `.apf2k8mod`, then use
  Build Game Folder. Field Art's separate copied-0A export contains only its
  selected texture. Do not replace one edited 0A with another single-edit 0A.
  The updated shared build compiles all staged Field Art layers in each package
  together and rebuilds the crest cache once for all selected teams.
- **Why does another APF crest need Retail coverage?** Multiple team crests
  compose with the Retail side-decal profile. Full-shell alters a shared model
  and is still restricted to one crest. Adding another team refuses with the
  reason and keeps existing edits. Format-59 DXT5A endzones remain unsupported;
  supported format-18 endzone layers retain their fixed compressed budgets.
  If a build reports overflow, simplify the art or choose another supported
  slot. Save the full error and receipt when reporting a different build error.
- **Did swapping emulators brick my XISO?** A crash or open handle does not
  demonstrate changed bytes. Eject the disc and close both emulators before
  launching the other one or replacing the output. Studio now refuses a disc
  it observes open elsewhere. Compare streaming SHA-256 hashes and file sizes
  before and after a session to establish whether it changed. Keep the original
  source and project so a modified output can be rebuilt.
- **What about the screen-edge artifact?** Rebuild from the original with
  widescreen v3. Compare the same camera and scene in 4:3 and widescreen, then
  with Hi-res off/on. Capture the full frame and play art on/off; mark whether
  the artifact follows the field, a player, the sky, or a fixed screen edge.
  A blanket widescreen fix is not established for the unidentified clip.
- **Dynamic card but ordinary kickoff?** Basic and Advanced leave dynamic
  kickoff off; Experimental enables it on this stack. A card alone proves
  neither the executable hooks nor the selected book's alignment. Check the
  build receipt for the XBE, kickoff alignment and return assignments.
- **Muffs, blocking, slow play or Berman/audio loops?** These remain separate
  gameplay investigations. Record the exact patch list, output hash, emulator
  settings, scene, and frame counter. Compare one owner at a time from the same
  original source. A larger disc file does not mean the entire disc is in RAM.
  The research verdicts and witness recipes are in ASTRA_DISCORD_BUGS_2_REPORT.md.
