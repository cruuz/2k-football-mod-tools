# Editor fixes and common questions

These answers describe the Discord bugs update after its protected UI wiring is
integrated. The accompanying report distinguishes shipped code from that handoff.
No new game behavior has been witnessed in this work.

- **B3, update notice:** The updater compares known RC version labels with their
  matching beta release tags. If the notice still appears after restarting,
  check the version and folder of the copy you opened. Update now is available
  only when the release includes the matching SHA-256 verification file.
- **B7, repeated choices:** Selecting the same option in Gameplay and Build does
  not queue the patch twice. Both views use one choice after this update. Review
  the source, output and selected changes before making the disc.
- **B9, unchanged output:** A build that produces identical bytes says
  "No changes written". Check whether the patches are already installed on the
  source and whether you opened the output named in the receipt.
- **B22, saved Gameplay choices:** Gameplay choices are saved with your project
  after this update. Review them after reopening an older project, because
  choices missing from an old file cannot be recovered automatically.
- **B17, disabled buttons:** Open a disc and make a project edit or select a
  Gameplay change before making a disc. Check my images checks staged images;
  selecting only Gameplay changes gives it no images to check. The button's
  help text explains what is missing or whether another operation is running.
- **B11, stock textures after reopening:** Open your original disc and load
  your saved .2k5mod project to continue editing. A modified archive that the
  editor cannot read is refused instead of being shown with cached stock art.
- **B14, short first names:** Use the native Rosters editor. It supports names
  up to 15 characters when the shared name pool has room, and can reuse an
  existing name. If the pool is full, the message gives the required space and
  suggests reusing a name or shortening another name.
- **B16, WinError 193:** Extract the Windows xemu download and choose xemu.exe
  in Set up xemu. Choose a build for your PC's CPU type. A 64-bit xemu needs
  64-bit Windows; a shortcut, archive or program for another operating system
  cannot be launched as xemu.
- **B12, missing portraits:** A player's Photo ID chooses a numbered portrait;
  changing the name does not change the picture. Replace that portrait and
  include both your portrait project and roster edits in the same disc build.
  An existing game save keeps its own Photo ID and may need editing too.
- **B10, Photoshop imports:** Photoshop PNGs are supported, including RGB,
  RGBA, indexed, grayscale, 16-bit and interlaced PNGs. Keep the exported
  texture's exact dimensions. DDS import is not supported in this PNG lane;
  export the base image as PNG while keeping its alpha channel. The error
  identifies a wrong size, corrupt file or other unsupported input.

## Replace a roster player's portrait

1. Open your original disc. In Rosters, select the player and record the Photo
   ID. Choose an existing ID in the portrait picker when assigning a picture.
2. In Find player images or the portrait asset browser, find that numbered
   portrait. For example, Photo 1234 selects Portrait 1234. The historical name
   on its label is only a description of the original owner.
3. Export the portrait, edit the 128x128 image and import the PNG into the
   project. The game stores a palette image, so Check my images can report
   color reduction needed to fit its fixed slot.
4. Export the roster edits to Build and check the roster edits option. Save
   your .2k5mod project, which contains the authored portrait replacement and
   Build choices. Custom roster JSON, playbook packs, artwork folders and other
   files referenced by Build choices must remain available at their saved paths;
   saving choices does not embed those external files.
5. Make the disc from the open project. The confirmation must list the shared
   project and roster edits, along with the Gameplay choices you want. Keep
   the output receipt and use its output path when launching.
6. For an existing roster or franchise save, edit its Photo ID too and save
   a signed copy. A changed disc roster affects a new game roster; it does not
   rewrite an existing save. Check the picture in game after integration.

PNG color profiles are accepted as metadata. The importer does not perform ICC
color conversion. It converts 16-bit channels to the high eight bits and keeps
transparency comparisons at full precision before that conversion.
