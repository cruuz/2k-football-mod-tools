# Beta 75 A2: ability-based charge cap

Status: **bounded offline proof; gameplay UNWITNESSED**. Urianus's September
21, 2026 Xenia Edge report supplies the gameplay observation. This job does
not claim to have witnessed a patched match. The two supplied stills show
Sims and Sanders selected, but cannot independently establish a charge time
or successful special-move animation.

## Pinned inputs and layout

Retail `default.xex` SHA-256:
`981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f`.
Decoded BASE: `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`.
Reconstructed TU 1.1:
`65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457`.
TU package: `5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b`.
Xenia module hashes: BASE `5447E5428AA2D52A`, TU `CEA825F7C2012F5A`.

The existing static-recomp guest bootstrap supplies the XEX metadata parser,
input pins and `xex_extract_pe.cpp`/XenonUtils extraction path. The generated
recompilation corpus is absent from this checkout. Analysis scans the decoded
PowerPC instructions, and execution reuses the existing Unicorn PPC machine
from `apf_playcall_research_probe.py`. This is a bounded emulation proof, not
execution of generated C++ or a full title bootstrap.

All routine addresses below are guest virtual addresses in **`.text`**:
BASE `84630000..84D0904C`, TU `84630000..84D0A01C` (exclusive ends).
Decoded-image offsets are address minus `82000000`. These are not compressed
XEX file offsets. PE `.text` raw pointers are `0262C800` / `0262CA00`;
the decoded image is addressed by RVA, not by those raw pointers.

| Purpose | BASE | TU 1.1 | Pinned surrounding words (BASE; TU difference stated) |
| --- | --- | --- | --- |
| Packed tier getter | `846300C0` | `846300C0` | `81630010 5563BFBE 4E800020` |
| Charge update entry | `848C51C0` | `848C5FF8` | `7D8802A6 48311C21 DBC1FFC0 DBE1FFC8`; TU call `48311DB9` |
| QB arm gate entry | `848C5214` | `848C604C` | `817D0044 3B800001 816B0028 5569077A` |
| Rocket Arm test and branch | `848C5220` | `848C6058` | `5569077A 2B090000 409A001C` |
| Laser Arm test and branch | `848C522C` | `848C6064` | `556B0738 2B0B0000 409A0010` |
| No-arm input clearing | `848C5238` | `848C6070` | `816A0018 556B07B8 916A0018` |
| Hook, roster pointer and tier word | `848C5288` | `848C60C0` | `817D0044 816B0010 556B056C` |
| Gold comparison | `848C5294` | `848C60CC` | `2B0B0200 409A0010 2F1C0000` |
| Passing-mode exclusion / cap flag | `848C529C` | `848C60D4` | `2F1C0000 3B600001 419A0008 3B600000` |
| Resume | `848C52AC` | `848C60E4` | `3D6084F4 390BF8F8 81680000` |
| First-level transition | `848C545C` | `848C6294` | `217B0000 815F01A8 7FA3EB78 D3FF00FC 7D6B5910 556B07BC 396B0003 516AB1D2` |
| Continue from level 1 | `848C54C0` | `848C62F8` | `2F090000 419AFE24 2F1B0000 419AFE1C` |
| Second-level saturation | `848C5534` | `848C636C` | `C1AB0AC8 FF006800 4099FDAC 817F01A8 39400003 7FA3EB78 D1BF00FC 514BB9D2` |
| Caller controller check | `848D6C14` | `848D7A9C` | `817C0000 2F0BFFFF 409A0014 7FC3F378` |
| Automation helper call / CPU bypass | `848D6C24` | `848D7AAC` | `4805768D 2F030000 419A000C`; TU call `480576CD` |
| Charge-update call | `848D6C30` | `848D7AB8` | `7FC3F378 4BFEE58D`; TU call `4BFEE53D` |
| Automation predicate | `8492E2B0` | `8492F178` | `81630040 816B0024 2B0B0000 419A0020 814B01B4 2F0A0002 409A0014 816B1368 7F0B1840 38600001 4D9A0020 38600000 4E800020` |

The cap block is identical in the two versions; the delta is `E38` only for
this function family. The caller uses `E88`, and its helper uses `EC8`.
The tests execute both versions rather than assuming one universal TU delta.

## Reading and decision table

`save_roster_players.py` stores tier in byte 18, low three bits: 0 None,
2 Gold, 4 Silver, 6 Bronze. The runtime getter uses
`(be32(roster+0x10) >> 9) & 3`, yielding 0/1/2/3. The charge routine instead
retains mask `0x600` and compares it with `0x200` (Gold). Neither form reads
an isolated tier byte. The static search follows roster-pointer loads at
`+44`, word loads at `+10`, `rlwinm` masks `0x600`, then the `cmplwi 0x200`
Gold comparison. The three-instruction tier getter independently confirms
the packed-field interpretation.

The player object points to the packed roster at `+44`, input state at `+10`
and dynamic player state at `+14`. The latter stores charge as a float at
`+FC` and charge state in word `+1A8`, bits 22..24. The original cap flag
`r27` is true only for Gold and `r28 == 0`. Past 1.0, that flag selects state
5 (continue toward 2) instead of state 3 (hold at 1). State 6 is the saturated
second-level state. The routine does not literally return integer 1 or 2;
the table reports the final charge float after bounded held-input updates.

| Held-input context | Retail | Patched |
| --- | ---: | ---: |
| Gold + Finesse | 2 | 2 |
| Silver + Finesse | 1 | 2 |
| Bronze + Ankle Breaker | 1 | 2 |
| Silver/Bronze + Club | 1 | 2 |
| Gold, no charged ability | 2 | 1 |
| Other tier, no charged ability | 1 | 1 |
| None tier + charged ability | 1 | 2 |
| QB passing mode, Laser Arm or Rocket Arm, any tier | 1 | 2 |
| QB passing mode, neither arm ability, any tier | 0 | 0 |

**QB qualification:** passing mode here means player byte `+34 == 0`, input
word `+18` bit 3 clear, and game-state `+130 == 0`. Passing/runner labels
interpret those conditions; their live UI-state mapping still needs a witness.
In that mode, the gate
reads roster word `+28` masks `4` and `8`, which are byte 43 bits 2 and 3.
With neither arm ability, it clears the held-charge input bits. Those gate
instructions remain byte-identical. With an arm ability, the retail mode
flag still prevents level 2 even for Gold. This bounded result qualifies the
reported Gold QB halo; it is not evidence that the tester's observation is
wrong. In runner mode (input bit 3 set in the fixture), the ordinary tier cap
applies. The patch replaces the shared tier/mode cap, so armed passing QBs
also gain level 2. A QB carrying another charged ability still cannot evade
the no-arm passing gate.

**CPU qualification:** the caller skips this entire update when controller
slot is `-1` and the helper returns zero. The helper returns true when the
team automation object exists, its `+1B4` field is 2 and its selected-player
pointer at `+1368` equals this player. Thus selected automation can enter the
same tier-capped routine, while the ordinary CPU bypasses it. Both branch
outcomes execute in the tests. The CPU's subsequent special-move selection
and animation are outside this proof; no claim that every auto-control mode
is exempt is warranted. This patch leaves that caller branch unchanged.

## Charged abilities and authored patch

The primary ability descriptions are in the retail `.string_` section, BASE
`84500000..8462C7DB` and TU `84500000..8462C803`. The five ball-carrier help
descriptions start at BASE `8461C1B8/C228/C298/C308/C380`; the five defender
descriptions at `8461D180/D1E0/D248/D2A0/D2F8`; the two QB descriptions at
`8461D358/D3B8`; and the combined move descriptions at
`8461D628/D690/D720`. TU adds `28` to these string addresses. Their first
four UTF-16BE code units include `0050 006C 0061 0079` (Player),
`0044 0065 0066 0065` (Defender), `0050 0069 006E 0070` (Pinpoint) or
`0051 0042 0020 0068` (QB h). The retail tutorial at
`845F81E8` also identifies the five individual ball-carrier abilities.
The contemporary [ability preview](https://www.gamespot.com/articles/all-pro-football-2k8-special-abilities-spotlight/1100-6173514/)
provides a secondary cross-check; executable strings and packed coordinates
are the implementation evidence.

| Packed byte | Mask | Abilities |
| --- | --- | --- |
| 36 (`24`) | `0F` | Ankle Breaker, Arms of Steel, Battering Ram, Cyclone |
| 37 (`25`) | `80` | Stop on a Dime |
| 42 (`2A`) | `01` | Swim |
| 43 (`2B`) | `FC` | Bull Rush, Club, Rip, Spin, Laser Arm, Rocket Arm |
| 44 (`2C`) | `0E` | Finesse, Power, Finesse and Power |

The corresponding big-endian word masks are `+24:0F800000`,
`+28:000001FC`, `+2C:0E000000`. No generic bonus or uncharged ability grants
level 2. The test covers each bit in bytes 23..44 at all four tiers, including
all unrelated bits, against both the emitted leaf and the retail state machine.

Only the word at the hook changes in retail code: `817D0044` becomes
`48447E78` (BASE) or `48447040` (TU). A 76-byte authored leaf occupies
`84D0D100..84D0D14C` within the 128-byte zero reservation
`84D0D100..84D0D180`. This is after the PE `.text` virtual/raw end but inside
the XEX code page `84D00000..84D10000`, descriptor `0x11`. Both entire
reservations are verified zero. No aligned absolute pointer into the
reservation exists in either decoded image; computed references remain a
limitation. Fourth-down's `84D0D000..84D0D040`, pass-fetch's
`84D0E000..84D0F000` and the situation patch are disjoint.

The leaf sets `r27` to any-charged-ability, uses scratch `r11` and changes CR6
only. It never changes SP, LR, CTR, CR0, floating-point registers or any other
GPR. A full-width instruction oracle checks register preservation independent
of the PPC32 harness. Twenty authored words comprise the hook plus leaf.
Apply checks the full image hash, original cap/gate words and zero cave.
Revert checks every authored word, restores the hook/zero cave and requires
the full original image hash again. Partial or foreign mutations are refused.

## Product and reproducible proof

`apf2k8_charge_abilities.py` follows the fourth-down canonical TOML/profile
contract. Standalone export defaults disabled and writes a JSON receipt with
addresses, original context bytes, masks, authored words and output hash.
Tools > Charged abilities adds export, explicit enable/install, status and
removal. The separate **Include ability-based charging patches in Build**
checkbox sets `ApfBuildOptions.charge_abilities`, false by default. It is a
session choice, not a serialized roster or project change. The normal APF
builder exports both enabled profile patches plus receipts only after this
opt-in and records the choice in its build manifest. As with fourth-down,
install the selected hash-keyed patch to make it active in Xenia. Building
alone does not install patches or rewrite compressed `default.xex`.

```sh
QT_QPA_PLATFORM=offscreen python3 -m pytest -q -s -p no:cacheprovider \
  tests/mod_editor/test_apf_charge_abilities.py \
  tests/mod_editor/test_apf_charge_abilities_native.py \
  tests/mod_editor/test_apf_charge_abilities_qt.py
python3 -m mod_editor.core.apf2k8_charge_abilities --profile tu_1_1 \
  --output /tmp/charge-review.patch.toml
```

The native fixture uses the complete pinned decoded image, synthetic player,
roster, input and game-state objects, and a 2,000-instruction bound per call.
Seven held-input updates with a 0.5-second timestep reach saturation. Charge
rate is an explicit 1-unit/second callee boundary; three notification callees
return without rendering/audio. No tier, ability, input, saturation or CPU
bypass decision is stubbed. The existing PPC32 adapter handles only the
callee-save 64-bit stack spills/restores on these paths. It is not a full
Xenon 64-bit execution witness. The representative Silver/Finesse calls peak
at 109 retail and 121 patched instructions in either profile.

Synthetic tests decode an authored uncompressed XEX, apply and revert the
flat image, compare all bytes and rewrap the original XEX exactly. Only the
whole retail digest check is mocked for that fixture; it is refused by the
production verifier. Native tests additionally restore the real input hashes.
Logs and the selected build/fourth-down regression file list are in
`reports/b75_a2/`. Missing XEX or Unicorn skips the native suite; missing TU
runs BASE only. Present mismatched inputs fail. Both owned profiles were
present for this job, as recorded in `decision-proof.json`.

## Integration boundary

The APF runtime contract now checks 177 shared capability rows and 74 APF
rows. The untouched 2K5 release checker and its beta-68 audit still hardcode
176 shared rows. Their count assertions need a coordinated integration
update before a combined 2K5 release; this job follows the explicit no-2K5
code scope. The APF capability, installer and static product checks use the
new counts. `packaging/repin.py --apply` reports zero pin changes.

## Urianus retest

1. Record Xenia Edge version, BASE versus TU 1.1, roster and other enabled
   patches. Restart with this patch removed. In the same practice play and
   field position, manually control Gold Barry Sanders and Silver Billy Sims
   with Finesse. Hold the charge input past the first ring and attempt both
   a juke and spin. Capture the entire charge interval, halo change and move.
2. Make fixture copies with stats untouched: Sims at Bronze and Gold; Barry
   at Gold with **all 15 charged abilities removed**; and a Bronze runner
   with only Ankle Breaker. Record the baseline level and move for each.
3. Add Club only to a Silver and a Bronze defensive lineman fixture. Keep
   their stats and play identical. Control them manually, fully hold charge
   and try the Club move against the same blocker; record halo and animation.
4. Tools > Charged abilities: select the actual executable profile, tick
   Enable patch for export / install, then Install enabled patch. The Build
   checkbox can also export both profiles for review. Restart Xenia and
   confirm the log applies the named patch to the matching module hash.
5. Repeat steps 1-3. Expect Barry+Finesse unchanged at 2, Sims+Finesse at 2
   for Silver and Bronze, Ankle Breaker/Club fixtures at 2, and Gold without
   a charged ability at 1. Check the actual special move, not only the halo.
6. For QB fixtures use Dan Marino with Laser Arm only and John Elway with
   Rocket Arm only, then make Gold/Silver/Bronze copies with stats unchanged.
   Also clear both arm abilities in copies. Test first while standing in
   passing mode, then after entering runner/scramble mode. Capture which mode
   produced the reported Gold level-2 halo. Armed QBs should reach 2 with the
   patch; no-arm QBs should still refuse charge in passing mode. Other charged
   abilities must not bypass that no-arm gate.
7. Repeat manual, CPU and auto-controlled versions of the same play; record
   the exact control mode. CPU bypass and selected automation are different
   branches. Confirm no regression in control switching or charge release.
8. Remove installed patch, clear the Build checkbox, restart and repeat the
   original Barry/Sims/Gold-no-ability checks. Expected retail table: 2/1/2.
   Save/reload, repeated plays, animation correctness and match stability
   require this in-game witness; the offline proof establishes none of them.
