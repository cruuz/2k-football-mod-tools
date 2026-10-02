# Official marks pack

Beta 76.1 saves the logos carried by SOFTDRINK 2K28 for your own builds. Click
**Install SOFTDRINK 2K28** on Share to install the finished disc and save its
logos. **Customize SOFTDRINK 2K28** and CLI apply also save them. If you already
installed with Beta 76, click **From a SOFTDRINK pack...** beside Official marks
pack on Build and choose your `.2k5patch`. This saves just the logos.

The Build row shows the saved pack's name and date. Studio keeps the logos in
its per-user data folder on Windows, macOS and Linux, so moving the original
pack does not remove them. A failed save keeps the previous valid selection.
The saved source record includes the pack name, version, SHA-256 and save date.

Beta 76 keeps club art and plain type in the public tree. New league, event,
broadcast and sponsor logos come from a separate local official marks pack.
Previously released assets remain unchanged.

The pack supplies 42 pinned PNGs for ESPN presentation marks and wipes/boards,
Modern MetLife, the MetLife model, SoFi, Highmark, Mercedes-Benz, U.S. Bank,
Lucas Oil and State Farm stadium models. Keep these options off to retain the
source's existing retail art. Enabling a dependent option without the pack
refuses with **Official marks pack missing** before output writes. A modified
source retains any art already installed in it.

Set `NFL2K5_MARKS_PACK` before starting Mod Studio, or set
`BuildPlan.official_marks_pack`. An explicit recipe path takes priority over
the environment; saved SOFTDRINK logos are the fallback. The chosen folder is
forwarded to stadium worker processes and recorded in the build receipt. For the ultimate
build driver's JSON recipe, add this field under `overrides`:

```json
{
  "official_marks_pack": "/path/to/marks_pack"
}
```

The folder contains `manifest.json` with schema `nfl2k5_official_marks/v1` and
a `marks` object. Each entry has a relative `file` and a `sha256`. The complete
list of keys, reviewed hashes and dependent features is in
`data/nfl2k5_official_marks_catalog.json`. The original five keys retain their
basenames; added keys use their former repository paths to prevent collisions.
All 42 entries must be declared. The manifest declarations and the requested
file's bytes must both match the public pins. Files must be bounded regular
files inside the pack. Invalid manifests, changed bytes and escaping paths
refuse cleanly, and cached pixels cannot bypass a fresh pack validation.

Mixed sponsor atlases are externalized whole to preserve their authored texture
contracts. The Rams right end-zone tile is split: its club lettering stays in a
public PNG, and only the isolated shield rectangle is restored from the pinned
private original. The reconstructed pixels must match the original pixel hash.
Other club tiles and midfield logos remain public. SoFi s40's ribbon, screen,
midfield event logo and shield are entirely supplied by the pack.

Development screenshots, composites and job reports are private evidence.
`packaging/b76_private_paths.json` records excluded paths and historical blob
identities. Release checks reject those paths and renamed copies of their
bytes. After integration, `tools/b76_externalize_marks_history.py` produces a
publication snapshot with the released base as its sole parent, verifies that
all excluded blobs are unreachable, and creates a local bundle. It never
pushes, changes tags or creates remotes. Review the final tree against beta-75
before using that procedure; it does not merge changes from the released base.
