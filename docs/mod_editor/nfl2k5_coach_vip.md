# NFL 2K5 coach VIP exports

This experimental Studio command builds 32 **user VIP saves** from observed
coach tendencies and the exact compiled SOFTDRINK playbooks. It supports the
native, manually selected Quick Game opponent. It does not attach 32 profiles
automatically in Franchise. Save exports and executable upgrades always use
new destinations; no save or disc is installed by these commands.

The implementation lives in `nfl2k5_coach_tendencies.py` and `nfl2k5_vip.py`.
The command is `python3 tools/nfl2k5_coach_vip.py --help`.

## Build the tendencies

`data/vip/coach_sources_2026.json` identifies each coach and the team/date/role
intervals attributed to him. `data/vip/coaches/*.json` contains computed
numerators, denominators, rates, sparse-sample fallbacks, and input hashes.
No tendency rate is entered by hand. Coordinator priors are identified in
each coach's provenance. A defensive coordinator's prior informs defense;
his new team's available 2026 offense informs offense.

The supplied PBP covers 2020–2025 plus 2026 weeks 1–4 through October 5.
The 2026 `home_coach`/`away_coach` strings contain outdated names, so the
audited role intervals take precedence. Team aliases include LA/STL → LAR,
ARZ → ARI, OAK → LV, and SD → LAC. The observed team offense is not necessarily
personally called by its head coach.

Pass calls include sacks and scrambles. Kneels, spikes, nullified plays,
special teams, and tries are excluded from ordinary offense counts.
Each charted feature uses only its known observations, preserving missing
values as `null`. FTN charting is joined by NFL game/play IDs for play action,
screens, box counts and pressure. Participation data adds man/zone and
coverage labels. Charting covers 2022–2026; coverage here covers 2022–2025.
ARI, BUF, CLE, and LV have no matched prior defensive coverage observations.

For example, supply every desired file explicitly:

```sh
python3 tools/nfl2k5_coach_vip.py derive \
  --source /private/pbp_2020.parquet \
  --source /private/pbp_2021.parquet \
  --source /private/pbp_2022.parquet \
  --source /private/pbp_2023.parquet \
  --source /private/pbp_2024.parquet \
  --source /private/pbp_2025.parquet \
  --source /private/play_by_play_2026.csv.gz \
  --charting /private/ftn_charting_2022.parquet \
  --charting /private/ftn_charting_2023.parquet \
  --charting /private/ftn_charting_2024.parquet \
  --charting /private/ftn_charting_2025.parquet \
  --charting /private/ftn_charting_2026.parquet \
  --participation /private/pbp_participation_2022.parquet \
  --participation /private/pbp_participation_2023.parquet \
  --participation /private/pbp_participation_2024.parquet \
  --participation /private/pbp_participation_2025.parquet \
  --out /private/new-coach-tendencies
```

CSV/gzip needs Python only; parquet input requires `pyarrow`.
FTN files come from [nflverse FTN releases](https://github.com/nflverse/nflverse-data/releases/tag/ftn_charting)
and coverage files from [nflverse participation releases](https://github.com/nflverse/nflverse-data/releases/tag/pbp_participation).
The [PBP](https://nflreadr.nflverse.com/articles/dictionary_pbp.html),
[FTN](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html), and
[participation](https://nflreadr.nflverse.com/articles/dictionary_participation.html)
dictionaries define the source fields. Exact source URLs and hashes accompany
the checked-in coach JSONs.

## Executable compatibility

Retail CPU policy works with the native VIP decision counters. The original
v0.6.1 **Modern 2** policy can force a fourth-down attempt after a VIP declines
its optional-go roll. A measured 21.7% VIP target consequently produced 100%
go calls in the original executable. Export rejects that known conflict.

The revised Modern 2 owner checks the native side accessor, CPU control,
playback mode and matching-book guard. For an active matching VIP, its
fourth-down, two-point and field-goal decisions delegate to retail policy,
including the retail mandatory charts. Native VIP optional rolls remain in
charge within their eligibility gates. Other CPU teams keep Modern 2 policy.
Play/target bonuses and defensive lottery exponents retain their existing
behavior. This does not establish full-game or overtime fidelity for a VIP.

New Studio builds using Modern 2 receive that revision. To prepare a private
copy of an existing verified installed owner:

```sh
python3 tools/nfl2k5_coach_vip.py upgrade-executable \
  --xbe /private/v061/default.xbe \
  --out /private/new-vip-aware-default.xbe > /private/vip-upgrade-receipt.json
```

The old Modern/Aggressive and v0.6.1 Modern 2 templates remain recognizable.
The upgrade stays inside the owner's existing 2,048-byte allocation,
verifies all old code and hooks, reseals the allocator and repins section
digests. Foreign or mixed inputs refuse. Modern/Aggressive upgrade to Modern
2; a retail executable needs no upgrade. The command creates an executable
copy, **not a rebuilt disc**. Integrate it into a new private game build before
using its decision behavior in xemu or on an Xbox.

Separate offense/defense playbook pairing bypasses VIP playback for the paired
side. Use the team's one exact book for both units. Re-export whenever the
compiled book changes, even if its visible name stays the same.

## Export signed saves

Supply a private copy of a valid USR save folder containing `SAVEGAME.DAT`,
`EXTRA`, and `TYPE`. No save template or title key is distributed here.

```sh
python3 tools/nfl2k5_coach_vip.py export \
  --tendencies data/vip/coaches \
  --image /private/compiled-game.xiso.iso \
  --xbe /private/new-vip-aware-default.xbe \
  --template /private/copied-USR-folder \
  --out /private/new-coach-exports
```

Omit `--xbe` to read the executable from the supplied image. Use repeated
`--team NYG` arguments to export a subset. The exact compiled menus determine
formation/play indices; the source catalog is not assumed to have identical
indices. Every team gets a directory of signed save files and a neighboring
JSON receipt containing book/save/executable hashes, selected plays, targets,
quantized rates, byte scope, missing plays, and retained template features.
The signed save remains exactly 20,720 bytes. `EXTRA` is the existing Studio
title-key HMAC-SHA1 signature. Twelve UTF-16 units are available for the name.

The writer preserves unknown bytes. It changes identity/name, matching book
index, the 20 offense and 15 defense histories, Coach's Pick counters,
derived run/pass situation statistics, and supported optional decision
counters. Crib progress, preferences, snap/play-call timing, onside behavior,
and unmapped historical statistics remain from the template. Those retained
statistics must not be presented as the real coach's career record. The live
Coach Matchup preview still displays those retained record/direction values;
the measured play-calling behavior is established by the native replay report.

## Select the opponent

Package the staging exports into Xbox **NFL 2K5 USR/VIP** save containers:

```sh
python3 tools/nfl2k5_coach_vip.py package \
  --exports /private/new-coach-exports \
  --xbe /private/new-vip-aware-default.xbe \
  --out /private/new-coach-transfer
```

Using your normal save-transfer process while the game is closed, copy the
package's 12-hex-digit directories into the existing `UDATA/53450030/` title
directory. Preserve all four files in each container and retain the existing
title-level metadata and icons. The commands do not edit HDD images.
The `NYG/` and other team directories are staging folders, not Xbox container
names. The native container ID is derived from the exact UTF-16 save name;
an unrelated disposable VIP folder is not interchangeable. A mismatched
folder/name caused a startup fault in the private transfer test. The package
command verifies signatures, receipts and names before producing the correct
layout. Its name hash matches native XAPI on all 32 names and 1,000 additional
random Unicode cases. Load the profile into the game before
opening Coach Matchup. The retail loader supports only
**four resident ordinary user VIPs**, including the human player's profile.
Keep the 32 exports as a library and load the opponents needed for a session.

The witnessed route, including the generated NYG Harbaugh profile on a copied
HDD, is:

1. Main Menu → **Play Now**.
2. In Team Select, choose the intended teams and use the left stick to assign
   the human controller to a side. Press **A**.
3. In Coach Matchup, choose **VIP Coaches**, press **A**, select the loaded
   coach profile, and press **A** again.
4. Confirm that the CPU side now shows that profile and start the game.

The right stick at Team Select changes the human's assigned VIP. **NFL
Coaches** is a different choice: it uses ROST coach records rather than these
learned USR histories. Naming a USR after a coach does not select a coach photo.
User VIPs display `vip_logo_a1`. ROST coaches display the `%04d` texture named
by their u16 portrait ID at coach `+0x40`; celebrity challenge profiles use
separate named celebrity textures. The private vp1 report contains the exact
32-team bitmap handoff for the portrait owner.

## What the save can represent

| Observed tendency | Native mapping and limit |
|---|---|
| Pass/shotgun joint rate | Eight eligible distinct calls in each of 20 offense rings; the ninth slot is the excluded cursor. Native previous-play exclusion remains active. |
| Down, distance, field, score, clock | Full descriptive PBP cells plus projection to native pools; native estimated time-needed is modeled at 120 seconds. Pools under 32 observations fall back to the coach marginal, then league only if necessary. |
| Play action/screens | Actual fake/throw and screen assignments. The exact v0.6.1 IND and NYG books have no callable screen; receipts expose the unmet targets. |
| Deep passing | First-read endpoint at least 20 yards, a called-route proxy for observed thrown air yards. It cannot force the eventual receiver or throw depth. |
| Run direction/gap | Native `281300` five-lane class, with record flip bit applied. NFL guard/tackle merge into inside; exact post-snap gaps and cutbacks remain unsupported. |
| Defense | Four eligible distinct formation/front/coverage tuples in each of 15 rings. Effective assignment chains provide man and five-plus-rusher proxies. All pools use the coach's charted marginal, not invented situation-conditioned rates. |
| Optional fourth downs | Counter from fourth-and-1..5, own 21..49, more than 120 half seconds. Native field/clock/kicker guards still apply. This is not an unconditional go percentage. |
| Optional two-point attempts | Counter after excluding the retail mandatory chart's cases from the observations. The game's mandatory decisions remain separate. |
| No huddle | Counter calibrated for the native burst of one initial call plus 2–4 extra calls; target uses eligible first-half PBP. Full-game rate depends on other native gates. |
| Audibles/presnap calls | The format records these, but they are not inferred from ordinary PBP. Presnap adjustment flags are neutral apart from the proven orientation flip; no coach-specific audible behavior is claimed. |

Small rings, formation availability and shared pass/shotgun constraints can
prevent a precise secondary-feature fit. All residuals are reported. Selection
of a callable play is not evidence that its on-field execution succeeds.
The optimizer keeps the quantized pass count fixed and may move shotgun by
at most 0.125 from its observed target, with a joint-distribution penalty.
This bounded trade-off improves run-lane and play-action fit when the
required calls exist only in under-center formations. It does not change the
predeclared native replay tolerances.

## Verify

The real-save unit tests are opt-in because retail inputs are private:

```sh
env NFL2K5_VIP_TEMPLATE=/private/copied-USR-folder \
    NFL2K5_VIP_XBE=/private/new-vip-aware-default.xbe \
    NFL2K5_VIP_IMAGE=/private/compiled-game.xiso.iso \
  python3 -m unittest tests.mod_editor.test_nfl2k5_vip -v

python3 -m unittest tests.mod_editor.test_nfl2k5_cpu_money_downs_m2 -v
python3 tools/nfl2k5_cpu_money_downs_assemble.py --check

python3 tools/b77/vp1_verify.py \
  --exports /private/new-coach-exports \
  --image /private/compiled-game.xiso.iso \
  --xbe /private/new-vip-aware-default.xbe \
  --retail-image /private/retail-extraction \
  --retail-xbe /private/retail-default.xbe \
  --samples 1000 --defense-samples 1000 --decision-samples 2000 \
  --tempo-samples 20000 --control-samples 100 \
  --out /private/new-native-replay.json
```

The bounded Unicorn harness runs the real binding, lifecycle, selectors,
RNG, compatibility accessors and run-lane classifier. Roster/player ratings,
clock state and kicker range are declared environmental fixtures. Retail
comparison uses the original team book and coach through native `2818D0`
statistics initialization and `281D90` game-plan selection in the same 20
situations. No full-game win/loss or execution claim follows from this test.

Predeclared absolute tolerances are 0.19 against the source-derived offense
pass/shotgun target after declared sparse-pool fallback and 0.07 against its quantized ring; 0.20 against defensive marginals
and 0.08 against the four-call ring; 0.05 for eligible optional decisions; and
0.015 for the continuous eligible no-huddle stream. Secondary proxies are
reported against a 0.15 target band and 0.07 quantized band. Those coarse
bands do not excuse an absent feature: missing screens and unsupported
outcome mappings remain explicit limitations even when a numeric band passes.

The generated NYG Harbaugh save loaded successfully at cold boot and was
selected on the CPU side of Coach Matchup in a copied-HDD xemu session.
Both human and generated VIP displayed the shared logo. That session used
the original v0.6.1 disc and verifies save loading/selection, not the repaired
decision policy or a full match.

The final 32-team sweep passed all declared bands across 2,016,000 native
draws, with zero ordinary offense/defense fallbacks. Across 640 offense pools,
mean pass-rate error was 3.319 percentage points for the generated VIP versus
17.866 for retail and 17.892 for the same book without a VIP. Shotgun errors
were 4.901, 60.584 and 36.358 points respectively. The largest individual
pass/shotgun errors were 10.844/14.672 points. Missing screens remain the
explicit exception in representable features described above.

All 32 final saves also passed the native loader and serializer in all four
slots on both retail and upgraded executables (256 exact round trips).
Consult the private `vp1/REPORT.md` and its evidence JSONs for per-situation
tables, original failures and corrected reruns, and live-menu observations.
