# Community fixes, batch 2

These editor changes require the integration described in WIRING.md. Gameplay
results remain experimental and unwitnessed until the listed comparisons are played.

- **How do I arrange a 0-9 sheet?** Use equal cells in one row, one column,
  five columns by two rows, or two columns by five rows, and select that layout.
  Read left to right, then top to bottom, starting at 0. See
  [number sheet instructions](number_sheets.md) for dimensions, padding and alpha.
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
