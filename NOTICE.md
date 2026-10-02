# NOTICE

## Scope of the licence

**IMPORTANT: The [MIT licence](LICENSE) covers the modding tools and their
original source code only. It grants no rights to any game, game data,
trademarks, or other intellectual property owned by SEGA, Visual Concepts, 2K,
Take-Two Interactive, the NFL, NFL Players Inc., or any other rights holder. You
must supply your own legally obtained copy of any game you mod.**

That paragraph previously lived at the bottom of the `LICENSE` file. It has been
moved here unchanged so that `LICENSE` contains the MIT text and nothing else,
which is what licence scanners — including GitHub's — need in order to identify
the project as MIT. Moving it changes no terms: the MIT grant and the paragraph
above both apply exactly as they did before.

## What these tools ship, and what they do not

These editors contain **no game data**. No ISO, no extracted game files, no
textures, audio, screenshots or rollback bytes are included in this repository
or in any published release archive. Both release archives are built from an
explicit allowlist and pass an automated **retail-free gate** that fails closed
if a game byte, decoded pixel, decoded audio sample, private path or undeclared
file appears in them.

The tools read a copy of a disc image or extracted folder that **you** supply,
and they only ever write to a **copy**. Your original disc image is never
modified.

## Third-party components

| Component | Where | Licence |
| --- | --- | --- |
| [XboxDev/extract-xiso](https://github.com/XboxDev/extract-xiso) 2.7.1 (`b72e5b6`) | `tools/vendor/extract-xiso/` — bundled as Linux ELF and Windows PE builds in the APF release archive | see `tools/vendor/extract-xiso/LICENSE.TXT` |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the MetLife Stadium outline, pitch and gate buildings (ways 24221553, 180559973, 230056157, 230056159, 230056162, 230056176, 230056181), converted to metres | `data/nfl2k5_metlife_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the SoFi Stadium canopy (ways 748790339, 748790321), YouTube Theater (963712167), Rivers Lake (893943661), NFL Media (836160473) and Kia Forum (26320999) outlines, converted to metres in the game frame | `data/nfl2k5_sofi_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Highmark Stadium (Orchard Park) facade outline (way 1339149058), the parking lots, roads and neighbouring buildings round it, converted to metres in the game frame | `data/nfl2k5_highmark_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the AT&T Stadium (Arlington) outline (way 47086748), the parking lots, roads and neighbouring buildings round it, converted to metres in the game frame | `data/nfl2k5_att_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Levi's Stadium (Santa Clara) building outline and bowl rim (relation 14507664), the pitch (way 357300430), the parking lots, roads, light rail, creek and neighbouring buildings round it, converted to metres in the game frame | `data/nfl2k5_levis_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Allegiant Stadium (Paradise, NV) building outline (way 691478555), the parking lots, roads and neighbouring buildings round it, and the Las Vegas Strip's towers of 60 m and more (Overpass), converted to metres in the game frame | `data/nfl2k5_allegiant_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Mercedes-Benz Stadium (Atlanta) building outline (way 536744534) and downtown and Midtown Atlanta's towers of 60 m and more (Overpass), converted to metres in the game frame | `data/nfl2k5_mercedes_benz_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the U.S. Bank Stadium (Minneapolis) building outline (way 743461508), the plaza, parking lots, roads, parks, rail, neighbouring buildings and downtown's towers round it, converted to metres in the game frame | `data/nfl2k5_usbank_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Lucas Oil Stadium (Indianapolis) building outline (way 27258709), the parking lots, roads, rail, neighbouring buildings and downtown's towers round it, converted to metres in the game frame | `data/nfl2k5_lucas_oil_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the State Farm Stadium (Glendale) building outline (relation 7370103), the parking lots, roads, parks and neighbouring buildings round it, converted to metres in the game frame | `data/nfl2k5_state_farm_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the surroundings of the modern stadiums for the shared environment kit (surface parking lots, roads and their lanes, parks and grass, water, trees and tree rows, buildings and their heights, land use round each site, tall buildings out to 15 km), converted to metres in each stadium's game frame | `data/nfl2k5_stadium_environment/*.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) elevation (Mapzen and the AWS Open Data Registry; its sources include SRTM (NASA) and USGS 3DEP, see [attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)): the terrain's elevation angle round each modern stadium out to 70 km, for its horizon band | `data/nfl2k5_stadium_environment/*.json` (`terrain`, `site_elevation`) and the band drawings in `data/nfl2k5_stadium_environment/art/` | the sources' own terms (public domain or attribution), per the attribution page |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the practice-field spacing and building sizes of nine NFL practice facilities, read as the dimensions of the composite practice facility (no map geometry ships) | `mod_editor/core/nfl2k5_practice_field_model.py` (`PARAMS`) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Hard Rock Stadium (Miami Gardens) pitch (way 171419978) that sets the game frame, converted to metres in the game frame | `data/nfl2k5_hard_rock_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Gillette Stadium (Foxborough) pitch (way 129176835) that sets the game frame, converted to metres in the game frame | `data/nfl2k5_gillette_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the Lambeau Field (Green Bay) pitch (way 145797338) that sets the game frame, converted to metres in the game frame | `data/nfl2k5_lambeau_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) data: the EverBank Stadium (Jacksonville) building outline (way 27258894), the pitch (way 172665883) that sets the game frame, Daily's Place (way 628324216), converted to metres in the game frame | `data/nfl2k5_everbank_model/footprint.json` | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), (c) OpenStreetMap contributors |
| [nflverse](https://github.com/nflverse) data (rosters, player and team history, play-by-play facts) | the historic season rosters in `data/nfl2k5_historic_rosters/`, `data/nfl2k5_retail_team_history.csv`, `data/nfl2k5_modern_names.csv`, the ratings references, the 2026 team specs in `data/nfl2k5_teams_2026/` and the 25th Anniversary moment facts; each file names its sources | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), nflverse contributors |
| [Wikipedia](https://en.wikipedia.org/) and [Wikidata](https://www.wikidata.org/) | some historic roster entries in `data/nfl2k5_historic_rosters/`, each linked to its source page | Wikipedia: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), Wikipedia contributors; Wikidata: [CC0](https://creativecommons.org/publicdomain/zero/1.0/) |

Build commands, toolchain and exact hashes for both bundled binaries are
recorded in `tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md`, so the
bytes can be reproduced rather than trusted.

## Trademarks

*ESPN NFL 2K5*, *All-Pro Football 2K8*, and all related names, logos and marks
are the property of their respective owners. The stadium models' venue and partner
wordmarks (for example U.S. Bank Stadium, Lucas Oil Stadium, State Farm Stadium, 3M and Land O'Lakes, from their Wikimedia
Commons public-domain files) are trademarks of their owners, shown only to depict
the venues as they stand. This project is not affiliated with,
endorsed by, or sponsored by any of them. Game names are used only to identify
which game a tool operates on.
