# WIRING: Beta 65 follow-up (MyCareer Settings)

## Beta 65 follow-up: MyCareer Settings (Astra, 2026-09-10)

This section supersedes the Stage 1 session-only Apartment toggle wording. The
runtime is already implemented on `astra/b65-supersim-2`; apply the protected
metadata edits below after taking this branch's explicit-path commits. No new
Build option, owner, preset switch or registry capability is needed. The existing
MyCareer option remains opt-in / EXPERIMENTAL / UNWITNESSED.

### Existing registry row

In `mod_editor/capabilities/registry.v1.json`, select exactly
`capabilities[id="nfl2k5.mode.my_career_inline"]`.

Replace its last `input_constraints` string (the one beginning `Supersim Stage 1`)
with:

```text
Apartment > Settings offers First Person Football Off/On (default Off), Off-field play Spectate/Skip presentation (default Skip presentation), and MyPlayer star On/Off (default On). First person calls the original Franchise Settings toggle at 0x147E60 and shares native word 0xE5FFE4. All three choices persist in the signed 128-byte career footer; old zero-filled footers load the defaults. B on Settings returns to Apartment. B during an eligible off-field presentation changes the saved choice to Spectate. Stage 1 remains at 1x; uninterrupted drives, headless fast forward and full-play-clock return remain unproved.
```

Append these paths to both `evidence` and `runtime.evidence` if absent:

```json
[
  "ASTRA_REPORT.md",
  "tests/mod_editor/test_nfl2k5_my_career_settings.py",
  "tools/mycareer_mode/settings_budget.json",
  "tools/mycareer_mode/settings_validation.json"
]
```

Append to `runtime.scope`:

```text
Settings menu dispatch, native row labels and yellow selection, the shared retail first-person word, all eight saved setting combinations, cold relocation/migration and bit-0-only MyPlayer star writes are proved in bounded native execution. A first-person snap and displayed in-game star still need Noah's witness.
```

Keep `runtime.status = "not-tested"`, the current classification, Build fields,
all preset defaults and the existing 16384 RX / 8192 RW description. Append to
`summary`: `Apartment Settings saves first person, off-field presentation and
MyPlayer star choices.` Do not change the separate prepared-save capability
`nfl2k5.mode.my_career`.

### RC89 / beta 65 changelog replacement

In `docs/mod_editor/2k5_mod_studio_changelog.md`, inside the existing
`## v1.0 RC89, beta 65` section, replace the complete bullet beginning
`**MyCareer Supersim, first stage` with this final wording:

```markdown
- **MyCareer Settings: first person, off-field play and MyPlayer's star.** Open Settings below Upgrades in the
  Apartment. First Person Football defaults Off and uses the same native toggle as Franchise Settings.
  Off-field play offers Spectate or Skip presentation, defaulting to Skip; both sides retain native AI at normal
  speed. MyPlayer star defaults On and changes only MyPlayer's star bit, preserving every other tag and player.
  All three choices now survive save/load, including migration of older careers. B returns from Settings;
  B during an eligible off-field presentation switches to Spectate. Native skips, menu dispatch, masked tags and
  saved choices are proved in bounded execution. Fast forward and a guaranteed pre-snap return remain unproved.
  The existing 16 KiB code and 8 KiB writable owners still fit, with at least 145 code bytes spare in the measured layouts; no other owner moves.
  Built by Astra; experimental, opt-in and unwitnessed. See `ASTRA_REPORT.md` for Noah's witness script.
```

### Release integration

`python3 packaging/repin.py --apply` refreshed the three changed MyCareer provider
pins in this branch. Regenerate the protected production cave manifest after all
integrated sources and central wiring settle. `.scratch/settings-manifest-final.json`
is a bounded XBE projection with current source snapshots and explicit historical
disc fields; it is not a release/disc-build manifest. The projection tool observes
the forward gate's actual writers and keeps every inherited retail reservation.

Keep the filled-star renderer enabled in the witness build. The Settings code
only manages MyPlayer's record tag; it does not install or redraw the filled-star
geometry. No optional ticker/camera rows or unproved Fast forward choice were
added. Packaged/offscreen integration belongs to Claude; game witnessing belongs
to Noah. No emulator or disc image was launched or built for this follow-up.
