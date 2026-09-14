# Beta 69 J4: weather and time of day

Branch: `astra/b69-j4-weather`. Base: `922c009d`. Work is limited to this
worktree. **EXPERIMENTAL; every in-game outcome is UNWITNESSED.**

## Delivered

| Requested item | Result | Evidence level |
|---|---|---|
| Climate table / small Weather editor | Implemented: per-stadium/month temperature, shared precipitation chance and wind; Undo; saved JSON plan; bounded ROST writer and reparsing verifier | PROVED offline writer and native reader |
| Modern NFL climate preset | An honestly named authored +2 °F outdoor example is implemented. A measured modern preset and relocated-city reassignment are deferred because no appropriate dataset is pinned locally | No modern climatology claim |
| Franchise time-of-day option | No no-op patch: retail already reads schedule hours and chooses all three variants; all 272 template slots executed. 9:30 AM ambiguity documented | PROVED native initialization; appearance UNWITNESSED |
| Franchise game-day weather choice | Not implemented: menu row suppression and later climate regeneration are pinned; no complete safe override lifecycle/slot proved | Pinned wall; proposed lifecycle HYPOTHESIS |
| Overcast/fog | One separate existing dry-weather haze endpoint option, 0.8 → 1.0; no new art or forced fog | PROVED data writer and native camera-field reader; appearance UNWITNESSED |
| Gameplay effects | Research only: six retail effective-rating penalties proved, other contact/wind consumers mapped | Bounded native block / pinned reads; played effects UNWITNESSED |

The editor is `tools/nfl2k5_weather_editor.py`. Both backends are OFF by default.
Their protected Build captions, all-preset defaults, preflight and write/read-back
code, GUI connection, **two** complete registry rows and manifest instructions
are in [WIRING_B69_J4.md](WIRING_B69_J4.md). The protected GUI/Build/registry/allowlist/manifest
files were not modified. Registered, rendered and usable are separate claims;
the standalone editor is implemented, and Build integration remains the
integrator's required step.

Core modules:

* `mod_editor/core/nfl2k5_weather.py`: resolves the relocated version-17 ROST
  stadium pool, pins identities/roof geometry, accepts finite bounded values,
  rejects duplicate/aliased/stale/mixed/foreign plans, compares float32 bytes,
  preserves the full resource outside requested floats and reparses after writes.
  Its Build adapter resolves outer 5 on the final disposable image. Version-18
  arena growth is refused. Source authoring never writes the disc or a save.
* `mod_editor/core/nfl2k5_weather_haze.py`: recognizes retail/applied coefficient
  bytes and pins neighboring table/reader spans, modifies one existing `.data`
  float and that section's digest, reparses, replays idempotently and restores
  exactly with Off. No new instruction, hook, cave or runtime storage.

The example preset adds 2 °F to 24 outdoor NFL home rows × 7 slots = 168 values,
relative to the loaded source. Repeated application does not accumulate the
change; one Undo restores the prior draft. It preserves wind and precipitation
and does not purport to be measured modern weather.

## Map, pins and corrections

Full map, formulas, all 82 stadium/city identities, team associations, 39 native
span pins and witness instructions:
[docs/research/nfl2k5_weather_time_of_day.md](docs/research/nfl2k5_weather_time_of_day.md).
The exact per-month floats and every matched stadium/sky entry are in
[weather_audit.json](reports/b69_j4/weather_audit.json).
Native numeric receipts are in [weather_native.json](reports/b69_j4/weather_native.json).
These are interpreted metadata and hashes, not retail fixture files or artwork.

Retail USA XBE: 11,948,032 bytes, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Important pinned sites are summarized below; the full byte-span SHA-256 table
is appended to this report.

| Storage / VA | Proved interpretation |
|---|---|
| Pack 0 outer 5, retail +`0x392800`, `0x90f80` bytes | Uncompressed main ROST with 32-byte wrapper |
| Resource root +`0x60`, table +`0xD0`, 82 × `0x80` | Stadium rows carry climate directly; city is row +8 pointer |
| Row +`0x28`, +`0x44`, +`0x60` | Seven float arrays: temperature, precipitation %, native wind |
| Team +`0x114`, active pointer `[0xE5FE64]` | Team-to-stadium linkage; heap data has no fixed retail VA |
| `0x4F6530`, `0x4F6564` | Month-to-slot lookup and three TOD temperature ranges |
| `0xEC870` | Native climate generator: temperature, precipitation, wind, haze outputs |
| `0xE3150`, `[0xE601D0]` | Six-choice Play Now generator and preset word |
| `0x15DB50`, `0x133FC0` | Franchise home-stadium selection and schedule-based climate/TOD generation |
| `0xE57C40 + 8*(17*week+game)` | Schedule record; +6 hour, +3 month; minute ignored by TOD decision |
| `0xE60184`, `0xE5FFA4`, `0xE5FFAC`, `0xE600C0`, `0xE60088`, `0xE600C4` | TOD, temperature, precipitation, wind magnitude/direction, haze globals |
| `0x77BB0`, `0x77BE0` | Snow/rain classification at 35 °F with precipitation >0 |
| `0x62BE0`, `0xE610A0` | Stadium suffix selection; `%s%c%c.iff` format; `d/a/n` then `d/r/s` |
| `0x62CCC..0x62CF3` | Indoor path resets generated weather after bundle naming |
| `0x85EF0`, `0x86190`, `0x2B9E0` | Existing haze table → globals → camera fields |
| **`0xA867F4`, file +`0xA7BE74`** | **Owned haze float: `cd cc 4c 3f` → `00 00 80 3f` (0.8 → 1.0)** |
| Chicago December at ROST +`0x388` | Example temperature edit: `cd cc e0 41` → `00 00 70 41` (28.1 → 15 °F); source pack offset +`0x392B88` |
| `0x17A6D0`, `0xAA4020`, `0x17A84B` | 28 effective-rating descriptors; six have precipitation bit 0; native penalty block |
| `0x2C11D9`, `0xF2FE0`, `0x133FC0` | Weather menu suppression, row disabled field and subsequent weather regeneration |

Climate table SHA-256:
`44d6e8566dc6902dd1f12dbe2625014687cc99f375559415231f72a634631cd2`.
Writer's preserved metadata/geometry SHA-256:
`ab4df547810a558fd3563b6bf4187b88a03b02111437b35a1f37e726a68cf85f`.
Normalized 60-byte haze table SHA-256:
`311636b9459867b8fb1fb57be66e6bee17660119754995f678f8f9e1f6642520`.

**Corrections to the leads:** the beta-33 “93 stadium / 279 sky sets, selector
never picks them” text belongs to the APF section of the hub handoff. NFL 2K5
has a working schedule-hour decision here. The bounded `sNN{d,a,n}{d,r,s}`
inventory matches 477 bundles (53 × 9), 324 named sky textures (36 × 9), plus
32 cloud textures. No matched texture name is fog/overcast/dusk; this is not a
claim about their appearance or unknown filenames. `s42nd.iff` resolves to
outer 3280 as the earlier group36 lead said. ESPN 25's editable SETUP dictionary
omits weather, but the native record contains weather +0x60, TOD +0x64 and
signed temperature +0x68.

**PROVED native findings:** the season slots are July/August, Sep, Oct, Nov,
Dec, Jan, Feb. March..June are invalid lookup entries, not editable independent
months. There is one precipitation threshold; rain versus snow derives from
temperature. Time selection is day for encoded hours 0..3/11/12, afternoon 4..5,
night 6..10. The 2026 template's 9:30 AM entries consequently select night;
the native eight-byte record has no AM/PM flag. No dynamic sunset is established.

The retail attribute penalty is additive to an intermediate effective value:
`-0.10 * precipitation` in rain, `-0.15 * precipitation` in snow. Speed, agility,
catching, pass accuracy, kick accuracy and hold-onto-ball have the descriptor
flag. Arm strength and kick power do not have this particular flag. The audit
records every descriptor's reader and hash. Contact interpolation at `0x1C75B7`,
table blending at `0x1DB968`, handling at `0x1DA057`, and wind vector paths at
`0x1CB7C5/0x1CBA1E` are additional pinned reads. The contact interpolation runs
natively: base 0.05 stays 0.05 dry, becomes 0.065 in intensity-0.5 rain and
0.075 in snow. Its continuation consumes hold-onto-ball and the Fumble slider
before a native random test. This is a fumble-related probability path, not
proof of friction. Final turnover activation, catching probability and distance
meaning remain HYPOTHESIS. The smallest localized future lever is rain's 0.08
literal at `0x1C75E2`, with full-path guards and downstream verification; no
gameplay writer was added.

**Pinned wall for the pregame choice:** Weather descriptors and arrow callbacks
exist, but mode/network filter `0x2C1140` suppresses the row in the relevant
mode paths through `0xF2F90`; `0x133FC0` subsequently regenerates conditions.
Unhiding a label or setting the Play Now preset alone would not establish the
requested franchise choice. A correct persistent override still needs a proved
screen route, initialization order and return/save lifecycle. Nothing is
registered for that deferred feature.

## Validation

Each new suite was run standalone, with the entire file executed:

```bash
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_weather.py
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_weather_native.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_weather_editor.py
```

Results: **11 climate tests OK; 10 native/composition tests OK; 2 offscreen editor
tests OK**, no skips in these final runs. Logs are in `reports/b69_j4/test_*.log`.
The climate suite includes whole-resource diff validation, float32 round trips
for all retail wind values, malformed/duplicate/aliased JSON, stale and partially
applied plans, relative-pointer relocation, Undo and the final image adapter
using a synthetic relocated outer resource with protected neighbors.

Native coverage: 82 rows × 7 months × 3 times = **1,722 climate calls**; every
hour 0..12 at four minutes; all **272** 2026 schedule entries; all six menu
presets; rain/snow boundary; native night/snow suffixes for edited Chicago
December; rating penalty and contact probability blocks; and camera haze field copies. Each invocation
has a 20,000-instruction cap and fails if it does not reach its boundary.
The native RNG is executed with controlled seeds, not stubbed. Section
permissions are preserved on complete mapped pages.

Haze tests cover idempotence, changed guard/table/scalar rejection, exact Off
restoration, no code-section changes, and both installation orders with
accelerated clock, franchise rules and helmet finish on the allocated full
request union. Their statuses survive, output bytes match and allocator replay
is unchanged. The native dry-haze camera value changes 0.20 → 0.25; tested
rain stays 0.825, snow 0.65, indoor/zero-haze stay zero.

An additional **complete owner-union composition** ran both orders using
`tests.nfl2k5_allocator_stack.compose(..., scaleout=True)`: haze after the full
stack and the full stack after haze. They produce identical bytes and haze Off
restores the complete composed baseline. Receipt:
[weather_full_composition.json](reports/b69_j4/weather_full_composition.json),
output SHA-256 `4e1c682b14e0a611df876a60496296da99d49715b03526152548178a39b4566a`.
Reproduction is pure in-memory patching of the read-only retail executable:

```python
from pathlib import Path
from tests.nfl2k5_allocator_stack import compose
from mod_editor.core import nfl2k5_weather_haze as haze
source = Path("extracted/ESPN NFL 2K5 (USA)/default.xbe").read_bytes()
base, _ = compose(source, scaleout=True)
left, _ = haze.apply(base)
right, _ = compose(haze.apply(source)[0], scaleout=True)
assert left == right
assert haze.apply(left, enabled=False)[0] == base
haze.verify(left)
```

The CLI was also run through real temporary resource/XBE output files, then
reparsed. The 168-value authored preset verifies, haze Off restores the entire
retail XBE byte-for-byte, and an existing destination is refused. All temporary
binary outputs were removed. Receipt: [weather_cli.json](reports/b69_j4/weather_cli.json).

Reproduce the read-only evidence generation with **new output names**:

```bash
python3 tools/nfl2k5_weather_time_of_day.py audit \
  'extracted/ESPN NFL 2K5 (USA)' weather-audit-new.json \
  --xbe 'extracted/ESPN NFL 2K5 (USA)/default.xbe' --assets
python3 tools/nfl2k5_weather_time_of_day.py native \
  'extracted/ESPN NFL 2K5 (USA)' weather-native-new.json \
  --xbe 'extracted/ESPN NFL 2K5 (USA)/default.xbe'
```

The default Python has PyQt5 and Unicorn here; missing optional dependencies or
retail files produce precise unittest skips elsewhere. No emulator, displayed
GUI, audio, network or full disc build was used. The harness stops before
filename formatting / GPU refresh where documented; it does not boot, play a
game, traverse a controller menu or load/reload a save.

The two supplied registry rows pass the current validator's structural,
domain and coverage checks when merged in memory: **161 → 163 rows**. Every new
row's backend, test and evidence path exists. A complete existing-file check is
blocked by the baseline registry's missing `docs/research/apf_audio.md` at row 0;
the protected registry was not changed. This pre-existing file gap is recorded
in [registry_validation.log](reports/b69_j4/registry_validation.log).

## XBE gates and integration

The four shared gate commands and final outputs are recorded below. They
enumerate the existing protected owner union. J4's haze
data writer is additionally covered by its dedicated native/composition suite;
integration must add it to the shared owner lists and rerun the enlarged union.
No new game instructions or runtime space were written; `REQUESTS`, `CAVES`
and `RUNTIME_GLOBALS` are empty. The owned existing `.data` scalar still requires
manifest registration. **Claude must regenerate the cave manifest after wiring
the combined stack.** `WIRING_B69_J4.md` supplies those precise changes and the command.

`python3 packaging/repin.py --apply` is run as the last writer-related operation
before each explicit-path commit. Repinning is not a substitute for integrating
the new owner or regenerating the release manifest.

```bash
PYTHONPATH=. python3 tests/mod_editor/test_xbe_patch_memory_writes.py
PYTHONPATH=. python3 tests/mod_editor/test_xbe_patch_cave_references.py
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
```

| Gate | Final output | Log |
|---|---|---|
| Memory writes | 115 tests in 1739.692s, OK | `reports/b69_j4/gate_memory_writes.log` |
| Cave references | 127 tests in 1920.227s, OK | `reports/b69_j4/gate_cave_references.log` |
| Pairwise composition | 388 tests in 2470.479s, OK | `reports/b69_j4/gate_pairwise.log` |
| Cave oracle | 29 tests in 390.058s, OK | `reports/b69_j4/gate_oracle.log` |

**All four gates are green before the final commit: 659 shared gate tests, no
skips or failures.** The 23 focused weather tests and complete haze/owner-union
composition are additional checks. Final repin output is retained in
`reports/b69_j4/repin.log`; it reported zero pin updates. The initial writer
commit is `b5917e88`; the editor/CLI commit is `781982dc`. The final commit adds
the contact-probability proof, evidence reports, changelog and integration handoff.

## Player witnesses and reporter attribution

All of the following are **UNWITNESSED**, including what anything looks like:

1. A new franchise on a disc with Chicago December set to the controlled
   cold/wet/windy example: record pregame conditions, successful entry/return
   and the Build receipt. The values are randomized baselines, not exact
   pregame promises. Compare the equivalent unedited source.
2. Same outdoor stadium in 1 pm, 4 pm and evening schedule slots: record the
   loaded variant and screenshots if useful. This checks existing retail
   selection, not a new feature toggle. Include a 9:30 AM template slot.
3. An indoor-stadium control with cold/wet authored data: witness the roof
   suppression path and normal game entry. Do not promise rain indoors.
4. Haze Off/On with equivalent nonzero dry outdoor conditions, plus rain, snow,
   zero-haze and indoor controls. Record if there is no discernible difference.
   A changed camera coefficient does not prove visible fog or better visuals.
5. An existing franchise save versus a new one, preserving the original save:
   adoption of the edited disc climate table by existing saves is unproved.
6. Gameplay observations with controlled ratings/sliders/weather and inputs:
   traction, catches, fumbles, pass/kick distance remain observations to collect,
   not results asserted by this patch. There is no snow-footprint implementation.

Changelog bullets under `## v1.0 RC94, beta 69` quote BigTimeEmpire's temperature,
wind and fog request; maumau78's dynamic-sunset question; newerest's gameplay
request and “insanity” comment; and Coach Edwards' actual APF heavy-rain reply.
The 9/13 Discord digest line 107 contains the quoted newerest text inside Coach
Edwards' reply; line 108 attributes the “insanity” sentence to newerest.
The changelog preserves that distinction rather than attributing the same
sentence to both people.

## Exact native span pins

| VA | File offset | Bytes | Purpose | SHA-256 |
|---|---|---|---|---|
| `0x00133fc0` | `0x123fc0` | 124 | schedule climate initializer | `79a8042a91a545c7007eed49fcf63d85a4b70efa3b48dad274a410f7a69ae7e6` |
| `0x0015db50` | `0x14db50` | 146 | franchise game setup caller | `d963a533b611c72a7115b51f87ed1304aa9b2aef4a29c7690d1d8a9fb33c6422` |
| `0x000ec870` | `0xdc870` | 382 | climate generator | `cdac3f6d6b1c1d5e68ffdeebd1f76a75ca7c09f7dda6969deb1ea362b17e2af1` |
| `0x004f6530` | `0x4eba50` | 52 | month lookup | `522714b8a1ccf37904b2028f805d6ad3bee4becc97b8395b56e75f3b31700a82` |
| `0x004f6564` | `0x4eba84` | 24 | time temperature ranges | `c22ac1432f759f9350472e04dbf374f0835f200b1eb497fb2e3bcd3857296e1a` |
| `0x000e3150` | `0xd3150` | 312 | Play Now weather generator | `30ddae291a46aa596297f38b0e1303301be106ae77012c5b884610957894dece` |
| `0x004f2524` | `0x4e7a44` | 24 | weather label pointers | `424e588384021f9fce3f3610b14caa1a018d1976b23b6037a934f85a89d750fd` |
| `0x00077bb0` | `0x67bb0` | 95 | snow and rain classifiers | `5c18644f31c7c71ac8aa3c5b389788ce29be30d9487932e3a6fa8f4528da9e5f` |
| `0x000e3130` | `0xd3130` | 31 | night and afternoon predicates | `86582c5004a7e1f2d7d624f31d145f1f0c5ac4124951282ff1d89dbbd5378ce0` |
| `0x00062be0` | `0x52be0` | 276 | stadium suffixes and indoor reset | `8d6d9dda83a1b4d88551451f4631adaacaac9311ab5e24e75139696fede6409a` |
| `0x002c1140` | `0x2b1140` | 211 | mode and network weather row suppression | `98edf2c8479f0d3b891979de9a5620085acf2c205c0936b0dd909096159d36ea` |
| `0x00085ef0` | `0x75ef0` | 160 | haze reader | `9a6c2b318862584e4831c20c289a3686cf206dc63df001a3cc57bf0758944777` |
| `0x00086190` | `0x76190` | 35 | haze camera dispatch | `a2dd6d42a842bb0da56a1acb2da8b76580acd0dd73b4769bb5a0fa15922374ae` |
| `0x0002b9e0` | `0x1b9e0` | 44 | camera haze fields | `136c6e1c847abc3701cb03299d6b8585a18e634701e6ca64c203de4f8f351b07` |
| `0x00a867f0` | `0xa7be70` | 60 | three haze parameter rows | `311636b9459867b8fb1fb57be66e6bee17660119754995f678f8f9e1f6642520` |
| `0x0017a84b` | `0x16a84b` | 73 | conditional precipitation penalty candidate | `c8c138e8ae989447257c9bfacd60c5badc0df8c37fa68876f8b4c1d9ccfb4afd` |
| `0x001c75b7` | `0x1b75b7` | 69 | wet ball contact interpolation | `e37caf541c6376d46cbb4aca84418820f156827f6bfc5ea3a6109b623d2ea6ea` |
| `0x001da057` | `0x1ca057` | 27 | wet handling candidate | `f012902cc60e8ab8b9f6240890d7fa2f6b66106f9c401a406ddf20b844dd5a1e` |
| `0x001cb7c5` | `0x1bb7c5` | 90 | wind vector candidate | `5e69681e4792727609582a10c7b38f8b5aa739c3de0b52692b89fa4a8d6a0cdc` |
| `0x001cba1e` | `0x1bba1e` | 95 | second wind vector candidate | `b9ade47a33b290d90f2bbe1ef0d499e8ee0dd837cc346ca8f3617be2a0e83e3f` |
| `0x00aa4020` | `0xa996a0` | 896 | 28 effective-rating descriptors; precipitation flag bit 0 | `03bf7526cbdad23e9574d87db9a35bad73a9367f14b5bf2e3180904f61d8c599` |
| `0x0025e3d4` | `0x24e3d4` | 137 | wind display divides native speed by 44.704 | `59a43161d24fa3d31ec24c9a4a3b4b97763673b333ec6fb44f69e202fe7314e9` |
| `0x004f267c` | `0x4e7b9c` | 4 | wind units per mph | `7c7d3deeaf065ff79ed7bde75182afab04cf390183c1bc5b46cd8aa3c3e62759` |
| `0x00e8b490` | `0xb1a170` | 60 | wind display format with mph unit | `16ee1079c287a822d51437643f70cfa408efa2042efd64c5887d497b47d2bf83` |
| `0x0014c110` | `0x13c110` | 82 | weather menu previous/next callbacks | `39ee5407d1fee5c824aa47970bcad608013ac0eb4e47c550dd95b4d2aa974981` |
| `0x002c2ca0` | `0x2b2ca0` | 82 | second weather menu previous/next callbacks | `39ee5407d1fee5c824aa47970bcad608013ac0eb4e47c550dd95b4d2aa974981` |
| `0x00340410` | `0x330410` | 82 | third weather menu previous/next callbacks | `39ee5407d1fee5c824aa47970bcad608013ac0eb4e47c550dd95b4d2aa974981` |
| `0x000f2f90` | `0xe2f90` | 112 | menu row disable and event dispatch | `efc9813a20ce4404b2af9baa1f66da33f72af332a532784602d2c7cc4a87bc1f` |
| `0x002c1200` | `0x2b1200` | 32 | mode filter jump table | `242a49ff0af6db8e527d15fa645321c6d317802eb617bf962aad12d368304d07` |
| `0x00502a38` | `0x4f7f58` | 32 | quick-game weather menu descriptor | `04a63e443ee9c9752c48226cbb37c8acf0587a221a9c8576cd41035399ec9dc7` |
| `0x00526bac` | `0x51c0cc` | 32 | weather menu descriptor | `024ff8e13358ba4e93bd824208f1b838e1a605e6bf2c3fd6bc310f1bba3787d9` |
| `0x00526ec4` | `0x51c3e4` | 32 | alternate weather menu descriptor | `024ff8e13358ba4e93bd824208f1b838e1a605e6bf2c3fd6bc310f1bba3787d9` |
| `0x0054fcc8` | `0x5451e8` | 32 | additional weather menu descriptor | `4713b3f6bcf8c97da218381ebb92b1f9fa00306ebe5a1bc074c184e514a399f8` |
| `0x0020cbd0` | `0x1fcbd0` | 160 | ESPN scenario environment loads | `f03d6eb97861ca3d06264c0ac8fce50c1194e69d350fadb6650f2a5cda50f60b` |
| `0x0017a6d0` | `0x16a6d0` | 452 | effective-attribute loop through precipitation block | `1a23ad6b877d27e0169b4ea6bc2c5b588991b6618db3bb14cdf2a5da114ab2eb` |
| `0x001db968` | `0x1cb968` | 124 | weather-dependent rating table blend | `a97d947d493d9ff70900e61e208a1928d1095b8288cb7720414f2855ee1c4300` |
| `0x00e610a0` | `0xaefd80` | 46 | stadium and created-field filename formats | `c48517d74bdc52bbc8239899780be7cd305a7fd8499cfdc153277e82c0ed9aae` |
| `0x001c7659` | `0x1b7659` | 123 | contact value through hold-onto-ball and Fumble slider tables to random test | `9d4ac61ca37834644e0050df6b9226862719f0d0696534c0d43cd7b4cdd9c178` |
| `0x001c5550` | `0x1b5550` | 34 | native probability random comparison | `8b1b19bada85bb0c74b1478cac19a632384678ff2674ab2400ec9537e3bee87e` |
