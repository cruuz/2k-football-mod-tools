# Modern helmets and facemasks (beta 76, EXPERIMENTAL / UNWITNESSED)

The Build tab option **Modern helmets and facemasks** (`modern_helmets`, off in every preset) gives the 2026 league's
Revolution helmet the details of a modern Riddell helmet and current facemasks, and keeps the 2004 equipment for the
classic scenarios.

## What the game has

NFL 2K5 has two selectable helmets and 27 facemasks. All of them live in the common player group (outer 3) and are
shared by every team; a team only supplies the art (`helmet00` for the Standard helmet, `helmet02` for the
Revolution, 256 x 256 P8).

| Slot | Roster field | Close up (`hi_head`, outer 3 chunk 115) | At distance (`lo_body`, chunk 113) |
| --- | --- | --- | --- |
| Standard helmet (shell A) | `+0x0C` bit 6 = 0 | `HI_HELMET_A` | `HI_HELMET_A` |
| Revolution helmet (shell C) | `+0x0C` bit 6 = 1 | `HI_HELMET_C` | `HI_HELMET_C` |
| Shell B | (no route) | the Guardian overlay's cap | the cap |
| Facemasks 0-26 | `+0x20` bits 10-14 | `FACEMASK00`..`FACEMASK26` (drawn in the kit's facemask colour) | `LO_FACEMASK` / `LO_FACEMASK_C` with the texture `maskNN` |

## What the option changes

* Helmet **Revolution** keeps the game's own shape and texture coordinates, so every team's helmet art (logos,
  stripes, wraps) maps exactly as painted, and gains the details of the **Riddell SpeedFlex**, the plurality helmet
  family on the 2026 NFL/NFLPA helmet poster: the flex panel's U-shaped cut across the forehead (the claimed design
  of Riddell's US D752,821), the temple, crown, rear and side vents, the jaw flap's seam and the rear shelf above the
  rear bumper. The crown and rear vents sit over the vents already painted in the team art.
* Facemasks **12-26** become fifteen current Riddell masks: SF-2BD-SW, SF-2BD, SF-2BD-HD, SF-2EG-SW, SF-2EG-SW-HD,
  SF-2EG-II, SF-2EG-II-HD, SF-2BDC, SF-2BDC-HD, SF-3BD, SF-KICKER and the Axiom W-2B-SW-HP, W-2B-HP, W-2BC-HP and
  W-2EG-HP, each with its low-LOD texture. Each mask is fitted to riddell.com's front and side product photos of
  that mask: its bars are traced on the front photo (so its width, height and bar layout are the photo's: wide at
  the top, flaring, shorter than it is wide) and their depth is read on the side photo.
* The **Standard helmet and masks 0-11 stay retail**. They are the classic set that the 75 historic teams and the
  25 Anniversary moments wear. The option moves those files' few other players onto that set: 34 Revolution records
  go to Standard and 26 masks go to the nearest retail mask.
* The league roster's equipment fields put the 2026 players in the modern parts: helmet 1 and a modern mask by
  position. They ship as a separate roster fragment.

## How it is written

* The details are thin parts 0.12 cm above the retail shell, placed by azimuth and elevation around the head and kept
  off the logos (a map of where the 32 team arts have logos, stripes and numbers). The mesh has no vertex colour, so
  their darkness comes from the texture: every detail vertex samples a texel that is near black in all 32 team arts.
* They are drawn by the helmet decal submesh (`LOGO_helmet_C`), which uses the same team texture without the
  shell's reflection weight, so the vents read as matte openings. That submesh's commands move into the facemask
  run's spare words (its own 26 retail indices first, then the details) and the details' vertices follow the masks
  in that run. The retail shell, visor, decals and accessories keep every vertex; the distant model is unchanged.
* The masks are placed at the photos' scale (the frame's outer width is the retail masks' 22.8 cm on this shell),
  their top bar under the front bumper. The Revolution is shallower than the helmet the masks were made for, so
  each mask's depth is compressed just enough that its frame reaches the shell's sides at the temples (80 to 85
  percent for the SpeedFlex masks, 65 to 70 for the Axiom); the lower frame then sits on the jaw flaps' edges and no
  bar enters the shell or the face. The SpeedFlex masks that share a frame on the photos share it in the model too.
  The distance plate's texture for each mask is drawn from the same 3D bars, carried onto the plate along rays.
* The owned parts are re-authored in place inside the existing player shape. The vertex counts, streams, skin
  palette and morph records stay as retail, and the close-up resource is refitted into its retail stored span with
  its wrapper unchanged (268,981 of 270,336 bytes). The decoded sizes are unchanged, so the option costs no memory.
* The **Guardian overlay** composes with the option in either order: the two edits touch disjoint bytes and commute.
  The details stay inside the cap wherever the cap covers the helmet. The Guardian helmet C trial is refused, since
  it reshapes the same shell.
* The historic fix is field level, so it composes with the historic moment rosters in either order.
* A research mode, `speedflex`, rebuilds the earlier SpeedFlex shell in slot C (`geometry_speedflex.json`); it is not
  part of a release.

Geometry: `data/nfl2k5_modern_helmets/geometry.json`, generated offline by
`tools/nfl2k5_modern_helmets_generate.py` from the user's retail disc. Pins: `data/nfl2k5_modern_helmets/pins.json`.
Tests: `tests/mod_editor/test_nfl2k5_modern_helmets.py`.

## Not yet witnessed

Nothing here has been seen in a played game by the owner. To witness it:

* a 2026 game close up (the coin toss and replays) and at distance;
* a historic team and an Anniversary moment, which should show the retail helmets and masks;
* Guardian caps in practice over helmet C.
