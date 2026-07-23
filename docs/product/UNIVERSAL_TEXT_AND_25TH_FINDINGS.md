# Universal Text and ESPN 25th Anniversary fixed-text spike

Status: integrated product capability, 2026-07-18. The writer is connected to
the shared catalog, project/session model, Text tab, and unified build provider.
The copied-XISO build and independent verifier pass; the remaining product
check is one xemu display spot check owned by the runtime lane.

## Product outcome

The private source index still contains 716 recognized text-bearing resource
banks. Before this spike, the product catalog exposed 17,588 decoded strings,
of which 13,416 were editable ROST strings. Strict decoding of the placeholder
banks adds 5,758 previously hidden strings, and the existing 1,115 STRG strings
gain a bounded writer.

The integrated Text tab exposes 23,346 strings, with 20,074 editable. This is
not an estimate: it is the exact result of parsing the recognized private
cache, and both values are rendered in the UI summary.

| Bank kind | Banks | Strings exposed after integration | Editable | Read-only | Product decision |
| --- | ---: | ---: | ---: | ---: | --- |
| ROST | 76 | 16,473 | 13,416 | 3,057 | Keep the existing bounded roster/identity writer and existing read-only fields |
| STRG | 2 | 1,115 | 1,113 | 2 | Unlock every nonempty fixed pool allocation; show alias count |
| SITU | 1 | 150 | 100 | 50 | Unlock four display strings per moment; keep team selectors and scenario logic read-only |
| CRED | 1 | 771 | 608 | 163 | Unlock every nonempty credit-string allocation |
| TRIV | 1 | 4,837 | 4,837 | 0 | Unlock category, subject, question, and four answers for every question |
| NAME | 635 | 0 user-facing strings | 0 | 635 banks | Label as player-name glyph metrics, not universal text |
| **Total** | **716** | **23,346** | **20,074** | **3,272** | |

The 635 `NAME` resources are not missing menu/player-name text. Each is a
160-byte player-name-atlas metric resource: one structural object label followed
by 29 pairs of 16-bit atlas offsets and advance metrics. They remain visible as
read-only indexed resources, but inventing string assets for them would be
incorrect.

## Shared safety contract

All four newly writable formats use UTF-16LE, NUL termination, and the same
field-local biased pointer convention:

```text
target = pointer_field_address + signed_stored_value - 1
```

The writer never changes a pointer, record count, lookup ID, wrapper, resource
size, archive extent, or XDVDFS directory entry. A replacement must fit inside
the original string plus terminator allocation. Shorter values receive a NUL
terminator and zero-fill through the rest of that allocation. Empty replacement
text is rejected. UTF-16 code units, not Python character count, determine the
limit.

Every edit is represented publicly by a stable logical asset ID and the user's
new text. Source pack names, physical offsets, original text, original bytes,
and preimage hashes are private build-time state. A shareable edit has this
shape:

```json
{
  "asset_id": "nfl2k5.text.situ.moment.0.title",
  "kind": "text",
  "value": "MOD"
}
```

`MOD` is test-authored text, not a retail string.

## STRG

The two STRG bodies were already exact parsers/serializers, but were previously
kept read-only because their archive writer and alias behavior had not been
admitted to the product.

- The primary body has 1,492 lookup records and 1,106 pool allocations.
- The secondary body has nine lookup records and nine pool allocations.
- Pool allocations total 1,115. Exactly 1,113 can hold nonempty text; two are
  terminator-only allocations with a character limit of zero.
- Aliasing is explicit. Editing one pool allocation updates every STRG lookup
  record that points to it. The UI must show `Used by N records` rather than
  pretending aliases are independent strings.
- Lookup IDs, record order, pool-start units, and resource sizes remain fixed.

Executable binding is exact: registration occurs at `0x00169270`, and the
loaded-table lookup at `0x001692D0` walks the same record layout and pool
references. The same-span writer therefore edits the actual loaded allocation,
not a disconnected text scan.

Stable selector:

```text
strg:<outer-index>:<chunk-index>:message:<pool-index>
```

## ESPN 25th Anniversary SITU bank

The single SITU resource is the 25th Anniversary moment/scenario table. Its
decoded body is 29,104 bytes.

- The descriptor is at body-relative `0x40`.
- The descriptor count is 25.
- Records begin at `0x44`, use a `0x6c` stride, and end at `0xad0`.
- Each record has six unique UTF-16 pointers at relative fields `+0x00`,
  `+0x04`, `+0x08`, `+0x0c`, `+0x14`, and `+0x18`.
- The first four are title, historical description, challenge objective, and
  date. These 100 allocations are editable.
- The last two are away/home team resource selectors. These 50 strings are
  browsable and exportable but read-only; changing them as ordinary prose would
  break resource lookup.
- All 150 targets are unique and form one contiguous string pool. There are no
  hidden aliases.

Executable binding is stronger than a content guess:

- `0x00165ee0` walks all 25 records at a `0x6c` stride.
- `0x002cfc40` fixes exactly the six pointer fields; `0x002cfca0` performs the
  inverse serialization.
- Registration starts at `0x00166000`, and the record accessor at
  `0x002cfd40` uses the same count/base and stride.
- UI paths at `0x0020c813` and the `0x002c59e1`–`0x002c5ac1` region consume the
  first four fields as display text.
- Separate code paths consume `+0x14` and `+0x18` as team lookups, which is why
  they are not admitted to the text writer.

Stable selector:

```text
situ:moment:<zero-based-moment>:<title|historical_description|challenge_objective|date>
```

### What remains unsafe in scenario logic

The record's numeric/state fields at `+0x10` and `+0x1c` through `+0x68` are not
universal text. They appear to carry the scenario setup, including team/stadium
relationships, score/clock/possession/field-state values, and conditions, but a
complete field map and range constraints do not exist. Unlock conditions may
also involve persistent profile state outside SITU.

The bounded corpus narrows the future decode without just naming fields by
guesswork:

- `+0x10` is a small identifier (1–30 across the 25 records).
- `+0x1c` and `+0x20` are year-like integers spanning 1966–2004 and are strong
  roster/season-year candidates, but their consumers have not been assigned.
- `+0x24` and `+0x28` are Boolean-valued in this corpus.
- `+0x3c`, `+0x48`, `+0x50`, `+0x54`, `+0x58`, `+0x5c`, `+0x60`, and `+0x64`
  are small enum/flag candidates.
- `+0x40`, `+0x44`, and `+0x4c` contain finite IEEE-754 values.
- `+0x68` is signed: most records use small positive values, while one uses a
  negative value. Treating it as an unsigned ID would already be wrong.

These observations are type/range evidence only. They are intentionally not
promoted to editable labels until runtime reads establish causality.

The product boundary is therefore:

- Moment title/description/objective/date: **Editable**.
- Team selectors: **Preview/Export-only** with a resource-lookup warning.
- Scenario values and unlock logic: **Coming Soon** with this findings note.

The best next spike is a single-moment runtime memory trace that correlates each
numeric field with the loaded scoreboard, clock, possession, field position,
and completion event. It should not begin with blind byte edits.

## CRED

The 29,856-byte CRED body has a count of 619 and a fixed `0x0c` record stride.
Each record contains one numeric credit-event type and two UTF-16 pointer
fields. The pool contains 771 allocations:

- 608 nonempty allocations are editable.
- 163 terminator-only allocations cannot hold nonempty text and remain
  read-only.
- One empty allocation is deliberately shared by 468 pointer fields; all other
  pool allocations have one reference.

The complete header, record table, pointer fields, pool, and zero trailer rebuild
byte-identically. `0x00166960` and `0x001669a0` are the paired pointer
fix-up/inverse routines. Registration uses the CRED FourCC at `0x00166db0`.
Rendering code in the `0x00166fe0`–`0x001671a8` region loads the two record text
fields and submits them to the text path.

Stable selector:

```text
cred:<outer-index>:<chunk-index>:string:<pool-index>
```

The numeric event type remains read-only.

## TRIV

The 242,848-byte TRIV body contains 691 records. Each record is `0x24` bytes:

| Relative field | Meaning | Product access |
| --- | --- | --- |
| `+0x00` | Question index/identity | Read-only numeric |
| `+0x04` | Category | Editable text |
| `+0x08` | Subject | Editable text |
| `+0x0c` | Question | Editable text |
| `+0x10` | Answer A | Editable text |
| `+0x14` | Answer B | Editable text |
| `+0x18` | Answer C | Editable text |
| `+0x1c` | Answer D | Editable text |
| `+0x20` | Correct-answer index | Read-only numeric |

The seven text fields produce 4,837 unique, nonempty allocations. There are no
aliases. The complete body rebuilds byte-identically. Registration occurs in
the `0x00166380`–`0x001663b3` block; `0x002cff60` and `0x002cffd0` process exactly
the seven pointer fields, and `0x002d0040` acquires the loaded TRIV resource with
the same 691-record count.

Stable selector:

```text
triv:question:<zero-based-question>:<category|subject|question|answer_a|answer_b|answer_c|answer_d>
```

The correct-answer index is deliberately outside Universal Text. A future
Trivia editor could expose it as a validated 0–3 choice without changing this
writer.

## Copied-XISO transport results

Four independent experiments used the recognized 6,300,499,968-byte USA Xbox
XISO as a read-only source. Each created a complete exact-layout copy, replaced
one allocation, then compared every byte of source and output. In every run the
source SHA-256 remained
`7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`,
the XDVDFS tree was identical, the replacement read back exactly, and no byte
outside the chosen allocation changed.

| Kind | Allocation bytes | Actually changed bytes | Output SHA-256 | Private receipt |
| --- | ---: | ---: | --- | --- |
| SITU | 26 | 12 | `b8106fad9a5fa98081a9629987ab6f324a33183ed44247bfe6e32bb24d2ae6ef` | `.codex-tmp/universal-text-spike/situ-title-transport-smoke.json` |
| CRED | 72 | 35 | `89286deeb0aa85ffbfbde0459878cb65d859f32a8e0dfcc2e950b5b1b1001292` | `.codex-tmp/universal-text-spike/cred-transport-smoke.json` |
| TRIV | 176 | 87 | `e563e73ae12339df6495e56112806852530d093472c1e7bc5c17fcccb7c71cb0` | `.codex-tmp/universal-text-spike/triv-transport-smoke.json` |
| STRG | 44 | 21 | `359e86d020e864aa317c329dd6c7b13fd54aef9228f708dc0eff106f7b96e532` | `.codex-tmp/universal-text-spike/strg-transport-smoke.json` |

The corresponding `.xiso.iso` files are private retail-derived test artifacts.
They live under `.codex-tmp`, are not release inputs, and must never be packaged.
These experiments prove source-to-copied-XISO transport. They do not replace the
single xemu spot check required when the capability is wired into the product.

The integrated unified backend was then exercised independently with
`situ:moment:0:title` and user-authored value `MOD`. Build and verify both
reported `edits=1`, `changed=12`, and output SHA-256
`b8106fad9a5fa98081a9629987ab6f324a33183ed44247bfe6e32bb24d2ae6ef`.
Its private project, manifest, bounded replacement, and 6,300,499,968-byte
copied XISO are under `.codex-tmp/universal-text-integration/`; none is a
release input.

## Integrated product contract

Implementation lives in
`mod_editor/core/nfl2k5_safe_text_banks.py`, with catalog/session/UI wiring and
the unified build route layered around it:

1. Build `SafeTextCatalog` from the private `SourceCache.pack0` and
   `SourceCache.inventory` after the existing text catalog is built.
2. Match STRG assets by their existing asset IDs and upgrade their access,
   reason, alias count, provider kind, and selector. Do not append duplicate
   STRG rows.
3. Replace the CRED, SITU, and TRIV placeholder banks with the decoded bank
   rows, and append their 5,758 assets.
4. Keep NAME banks visible but relabel their role as player-name glyph metrics.
5. Store the safe selector in private provider metadata. `provider_edits()` must
   emit one logical record per changed allocation:

   ```json
   {
     "kind": "universal_fixed_text",
     "selector": "situ:moment:0:title",
     "text": "MOD"
   }
   ```

6. During build, call `SafeTextCatalog.resolve_edits()`. It re-resolves the
   selector against the current private cache, checks the preimage hash, rejects
   duplicates/overlaps, and returns a bounded replacement for one archive pack.
7. Translate that private pack span through the XDVDFS file extent in the
   already-copied output XISO. The standalone smoke tool demonstrates this
   translation and exact comparison; the logical selector and public project
   schema never contain a physical offset.
8. Use the existing project replacement document unchanged. It already stores
   only `asset_id`, `kind`, and the user's replacement value, so per-asset
   revert, project-wide revert, undo, and shareability remain intact.

Live integration assertions:

```text
text bank count       = 716
text asset count      = 23,346
editable text count   = 20,074
safe-bank assets      = 6,873
safe-bank editable    = 6,658
```

## Release-data audit

The new core module, test, CLI, and this note contain no decoded retail text
corpus and no original allocation bytes. They derive values and preimages only
from the user's private cache. Public project records contain only stable asset
IDs and user-authored replacement text. The audit JSON contains counts and
capability flags only. The verification receipts contain hashes and logical
selectors, not decoded original text or physical offsets.

Therefore the implementation files are release-safe. The four private smoke
XISOs are explicitly not release-safe and must stay excluded by the packaging
allowlist.
