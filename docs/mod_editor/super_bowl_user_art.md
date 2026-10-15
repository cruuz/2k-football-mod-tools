# Super Bowl walls and your own Super Bowl logos

With **Anniversary: named previews and period fields** on, every Super Bowl moment gets its own event dressing on
the stadium's temporary surfaces: the field wall, the LED ribbon boards, board wings and corner boards, hanging
banners and the crowd's banners. Permanent venue signs keep their bytes. Row 34 (Super Bowl XXXVIII) is held.

## What is on the walls

- **Event art.** An original event plate for each game (a chamfered championship plate with the game's numerals in
  chrome from 2017, in the host city's colours from 2008 to 2015, or in a 1990s block serif before that), SUPER BOWL
  and the numerals in metal type, the host city and year, and ribbon boards laid out as an event band over a
  matchup band. No Super Bowl or broadcaster logo is copied; the network is plain type on a chip.
- **The NFL shield.** From the 2008 season on, the mod's own official shield
  (`data/nfl2k5_espn25_fields/row45/center_logo.png`). For earlier seasons (Super Bowls XXIII, XXV, XXXII, XXXIV,
  XXXVI and XLII) the build reads the period shield from your own retail disc (`s43dd.iff`, field texture
  `center_logo`), so no retail pixels ship.
- **Team logos.** The mod's own team logos. Four team-seasons the mod has no logo for show a plain club roundel:
  the 1988 Bengals (XXIII), the 1990 Giants (XXV) and the 1999 and 2001 Rams (XXXIV, XXXVI).

The art is drawn by `tools/nfl2k5_super_bowl_walls_art.py` into `data/nfl2k5_super_bowl_walls/`: for each surface a
base PNG and a `.marks.png` layer with the authored marks of its slots. The manifest lists every slot box.

## Your own logos (optional)

On **Build**, beside the official marks pack, **Your Super Bowl logos** takes a folder. **Create folder...** makes
`user_art/` with three empty folders and a `README.md` that lists every file name, the size to aim for, the largest
slot each file fills and where it appears. The recipe field is `BuildPlan.super_bowl_user_art` (a folder path, or
empty).

```
user_art/
  README.md
  super_bowl/   XXIII.png XXV.png XXXII.png XXXIV.png XXXVI.png XLII.png XLIII.png XLIV.png
                XLVI.png XLVII.png XLIX.png LI.png LII.png LIV.png LVI.png LVIII.png
  brands/       nbc.png cbs.png fox.png abc.png espn.png
  teams/        optional: CIN_1988.png NYG_1990.png STL_1999.png STL_2001.png for the four team-seasons
                above; CODE.png (for example NE.png) replaces a club's logo in every Super Bowl it plays,
                CODE_SEASON.png only in that season (the year the season began)
```

- Event logos are about 512 x 512 pixels, network marks about 512 x 256, team logos about 256 x 256. Any shape works.
  A transparent PNG is preferred; an image without transparency is placed as a rectangle.
- The build trims empty borders, fits the image by aspect inside each slot's safe margin, keeps its alpha and holds
  it to the slot's colour budget (48 colours by default) so the surface still fits the game's 256-colour texture and
  the stadium scene still fits its original span.
- Upper or lower case names both work. Files over 8 MB, over 4096 pixels on a side, fully transparent or not PNG are
  ignored, and the slot keeps its authored mark.
- The NFL shield is never taken from this folder.
- Nothing in this folder ships with the Studio or a SOFTDRINK pack.

The Build panel shows how many files it found. The build log then lists what happened, for example:

```
Super Bowl walls: your logos folder /home/me/user_art
Super Bowl walls: filled from your folder: brands/nbc.png (XXIII, XXXII, XLIII, XLVI, XLIX, LII, LVI); super_bowl/XLVI.png (XLVI)
Super Bowl walls: authored marks kept for: super_bowl/XXIII.png, super_bowl/XXV.png, ...
Super Bowl walls: ignored brands/cbs.png: not a PNG file
```

The same lines and a record of every slot's source are in the build receipt, in the `espn25_fields` step
under `fields` > `super_bowl_walls` (and each alias's `detail` > `super_bowl_walls` > `slots`).
