# Version-0 save fixtures

Portable generated fixtures are in `tests/mod_editor/test_nfl2k5_save_rost.py`.
They construct runtime and disc framing independently and retain opaque prefix,
suffix, unknown fields and arena bytes. No proprietary payload is bundled.

The real regression reads the two preserved local fixtures under
`NFL2K5_SAVE_FIXTURES` (default `/home/noah/Desktop/2K5-8 Editors/save_fixtures`),
then `f0` or `f1` / `UDATA/53450030/0B8506889D40/SAVEGAME.DAT`, with sibling EXTRA.
It verifies the full SHA-256 and existing HMAC before any round-trip/edit trial.
Missing fixtures are skipped with their exact path; hash/signature mismatches fail.

Both payloads are 720,044 bytes, inner version 0, root at file 0x320, arena ending
at 0x91320, 2,479 primary plus 68 secondary players, and 52 teams.

| Fixture | SAVEGAME.DAT SHA-256 |
|---|---|
| f0 | 56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8 |
| f1 | 255da39178695a69c01efad9237764cbbd88c63aa78cfe911c8e3b070b6215ed |

Do not copy these game-data saves into a public commit or release. Unknown save
kinds remain opaque; this fixture proves the framing and records, not a full
franchise schema or gameplay acceptance.
