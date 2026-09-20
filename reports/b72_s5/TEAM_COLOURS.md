# b72-s5 active team colours

Neutral coverage masks and team-specific accents are enabled in the sprite layout. The 32 NFL palettes come from the supplied `team_colors_official_2026.json`, excluding logo-detail-only colours. Historical slots retain s3's pinned retail source. Seven custom or undocumented slots use explicitly flagged charcoal/silver fallbacks until their own colours are supplied.

`nfl2k5_scorebug_teams.py` recomputes allowed lighter/darker variants from source colours and rejects foreign or insufficient-contrast entries. It does not trust a candidate's claimed hex or contrast. A forged Raiders pink candidate is rejected by regression test. Every one of the 52 compiled records carries asset code, team kind, wing, rim and plate colours. The native owner resolves code plus kind in a bounded 52-entry table. Shared identities have a common valid tint group.

Rims use their independently selected team colour instead of the old generic lightening operation. Wings use neutral white coverage with the existing alpha gradient reduced to 75 percent. Plate, clock capsule, play-clock capsule and possession pointer use the possessing team's plate colour. Clock and quarter ink are white for contrast. Glyph shapes and the existing visibility gate are unchanged. Brand marks and retained event artwork remain their own assets.

Raiders wing and rim are `#646464`, a darker variant of their supplied silver `#C8C7C7`; the possession plate and capsules are official black `#000000`, as Noah requested. Their fills contain no pink. The neutral template prevents old KC/DEN colours from multiplying into other teams' accents.

Jev processed all 42 prior review slots using two differently worded group-choice questions per slot in one request. Twenty-two agreed at confidence >=0.8. Twenty did not; they retain previously validated palette choices and are flagged for Noah. These are text/metadata decisions, not judgments over image pixels. Seven custom/undocumented fallbacks are also flagged. `accents/responses.json` retains the full live responses; `accents/decisions.json` records the gate decisions. The code independently checks membership and contrast.

Unresolved Jev groups: **BUF, TB, ARI, KC, IND, DAL, NYG, GB, NE, LAR, PIT, MIN, BRI, BRP, BWG, CHH, AMW, AFC, NFC, NFL**.

Palette information still needed for neutral fallbacks: **USER1, USER2, UDC, LAL, CES, BFM, LAD**.

[4:3 model contact sheet](all_teams_43.png), [16:9 model contact sheet](all_teams_169.png), [palette review swatches](accents/contact_sheet.png), [review reasons](accents/review.json).

The sheets cover all 52 slots. Each self-match displays that slot's home and away accents together, with possession on the home side. Native tests separately exercise both possession sides for every slot at both aspects, checking actual emitted vertex tints against the validated table. No non-NFL logo replacement is added by this work.

All palette roles pass white contrast >=4.5:1; the weakest selected plate is 4.682:1. Model label-core diagnostics are >=253 at 4:3 and >=254 at 16:9 across these sheets. These measurements use the descriptor's bright-ink core statistic; they are **uncalibrated predictions**, not proof of in-game contrast or a fix for the dark label. The GPU model still fails the three supplied screenshots; see [GPU findings](GPU_FINDINGS.md).

The revision-2 accent table increases appended data by 1,024 bytes after the final resource layout/alignment, from 323,808 to 324,832 bytes. The 400,000-byte ceiling and existing 4,096-byte RX / 128-byte RW allocations remain. The engine occupies 4,086 RX bytes including its dispatcher and legacy path, leaving only 10 bytes of RX headroom. The older revision-1 scene route is retained for baseline comparison.
