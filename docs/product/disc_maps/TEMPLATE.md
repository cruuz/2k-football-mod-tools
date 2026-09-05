# <Title> (<Region>) — PlayStation 2 disc map

Mapped <YYYY-MM-DD> with `tools/ea_disc_map.py` on the rig, read-only. Source: `<SERIAL>.map.json` (not committed; counts below).
Grades: [M] measured by the mapper, [S] sourced (cite), [A] assumed.

## Identity [M]

| field | value |
|---|---|
| image | `<name>.iso`, <bytes> bytes, <files> files / <dirs> dirs |
| boot file / serial | `<BOOT>` / **<SERIAL>** |
| boot ELF | <bytes> bytes, sha256 `<hex>`, PCSX2 CRC `<HEX>` |
| whole image sha256 | `<hex>` |

## What is on the disc [M]

| kind | files | notes |
|---|---:|---|
| TERF containers | <n> | <chains seen: DATA-only / COMP counts>; alignment(s) <…> |
| TDB databases (bare) | <n> | <paths> |
| ELF / IRX | <n> | boot ELF + drivers |
| other | <n> | <magics> |

### Containers that matter (largest and the ones a page would edit) [M]

| container | bytes | chain | members | codecs | decompressed formats | what it is for |
|---|---:|---|---:|---|---|---|
| `/DATA/….DAT` | … | TERF→DIR1→COMP→DATA | … | stored …, LZH1 … | MMAP …, SMF … | <one phrase, e.g. uniform textures> |

### Databases [M]

| where | tables (records) | schema id |
|---|---|---|
| `/DATA/….DAT` member <i> / `/DATA/….DB` | `TEAM` (33), `PLAY` (…), … | `<sig>` |

Distinct schema shapes: <n>. Tables shared with Madden 08/09 (`PLAY`, `TEAM`, `DCHT`, `INJY`, `COCH`, …): <list or "none checked">.

### Textures [M]

MMAP members: <n> across <k> containers; dimensions (top): <WxH ×n, …>. Faces / kits / UI split: <from container names, [A] where guessed>.

### Text and audio [M]

TEXT members: <n> (<bytes>). SCHl members: <n> in <containers>. Nested TERF: <n>.

## Page-by-page: what a studio could offer today (rungs as they stand, not as they could be)

| page | feeding containers | format | rung today | what lifts it |
|---|---|---|---|---|
| Uniforms & Equipment | | | | |
| Names, Numbers & Faces | | | | |
| Text & Team Identity | | | | |
| Field Art & Create-Team Art | | | | |
| Stadiums | | | | |
| Presentation | | | | |
| Menus & UI | | | | |
| The Crib | — | — | honest empty page | not a concept on this disc |
| Audio | | | | |
| Gameplay | executable | R5900 | unknown (code-patch scaffold) | translations |
| Playbooks & Plays | | | | |
| All Textures | | | | |
| Saves | — | — | honest empty page | saves are not the disc |

## Writers: what could be rewritten with what exists today [M]/[A]

- `DATA` containers and stored members: `ea_terf.rewrite_member` (exists). List: <containers>.
- `COMP` containers with LZH1 members: read only until an LZH1 encoder exists. List: <containers>.
- TDB rows: reader exists; writer needs the four CRCs and a verifier. [A] until built.

## Open questions (one line each, no speculation)

- <e.g. which MMAP members are uniforms vs faces: needs the name table or a dump>
