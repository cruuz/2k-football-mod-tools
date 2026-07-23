# APF 2K8 rebuilt `ROST` forensic comparison — 2026-07-18

## Completed experiment and result

This was a bounded, headless, read-only comparison of the untouched retail
`ROST` container and the exact combined, team-only, and player-only builds used
in the negative Xenia experiment. No GUI or emulator was run, no game volume was
modified, and the sealed Alpha 14 release was not touched.

The result has two parts:

1. **Positive structural isolation:** the outer archive directory, physical
   entry allocation, decoded root arrays, every relative pointer, IFF ownership,
   footer, and zero tail are structurally sound. The decoded changes are exactly
   the requested fixed-allocation strings—6 player bytes, 9 team bytes, or 15
   combined bytes—and nothing else.
2. **Negative causal proof:** an offline comparison cannot prove what the retail
   guest H7A decoder produced before the crash. The most likely defect is now
   much narrower, however: the identity writer sends the entire 2,294,304-byte
   roster through the generic greedy H7A encoder. That changes roughly 413,000
   of the 435,225 compressed payload bytes starting at payload byte 9 for a
   6- or 9-byte semantic edit. The repository already contains a ROST-specific
   token-preserving encoder, but the identity writer does not use it.

Therefore, this experiment **does not unlock roster writing**. It identifies the
generic whole-stream retokenization as the first defect candidate to remove and
provides exact, in-memory-verified next-runtime candidates.

## Exact inputs

All paths are relative to the project root
`/media/noah/Storage/for codex 1.0`.

| Role | Exact path | Full `0A` SHA-256 | `ROST` outer-entry SHA-256 |
| --- | --- | --- | --- |
| Untouched retail control | `extracted/All-Pro Football 2K8 (USA)/0A` | `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e` | `e98dd07b38caa73ea2ce91eed19bef68896f9b63830a9169af4b7f22d8788cc7` |
| Combined name edit | `.codex-tmp/apf-roster-name-runtime-game-alpha14/0A` | `0219e730233327a63a6b54c1baea691dd43065bc459197b3dcbd997a8ca43a4c` | `96985e90835dc8a06e17461b50cd97014597feee4cf1cdca18caef7a99622019` |
| Team-only name edit | `.codex-tmp/apf-roster-team-only-runtime-game-alpha14/0A` | `fea265d2a58a7c331fdab399c10ff93fb3f9d64b2acc417b6d2fb81a918f621b` | `a7dca20498b5179f85d5509c50e47ccf04f41d570d26652071ee9b3f5fbca960` |
| Player-only name edit | `.codex-tmp/apf-roster-player-only-runtime-game-alpha14/0A` | `47f9f4c293f8c791d1480f56bacc7b1eff1b9dc863327d282c06a55d32ee8471` | `018ab79eddb6f8fafdce1cf711be1f58eb8738f04535abcfdd753c83b7db2efe` |

The per-build `.apf2k8-mod-studio-build.json` receipts identify the source code
route as `apf2k8_roster_identity_patch/v1`, outer entry 1126, and the two stable
pool targets `apf:roster-name:1977` and `apf:roster-name:4776`.

The matching runtime result is recorded in
`reports/product/apf_roster_identity_runtime_20260718.md`: the clean control
boots, while all three changed builds stop at guest PC `0x84AB1D40` reading
`0x0000000270000000`.

## Outer archive and physical allocation

All four inputs parse to the same outer archive contract:

| Property | Exact value |
| --- | --- |
| Archive magic | `0xAA00B3BF` |
| Alignment | 2,048 bytes (`0x800`) |
| Entry count | 1,543 |
| Directory span | `0x0000..0x48AC` (18,604 bytes) |
| Directory SHA-256 | `2463120a5fd4aacec49e50585eb23a4fc3ee27759f7bd11b407d35a2ab809942` |
| ROST table index | 1,126 |
| ROST name ID | `0xBCEFFD46` |
| ROST physical `0A` offset | 47,699,968 (`0x02D7D800`) |
| ROST outer allocation | 436,224 bytes (`0x6A800`) |
| ROST physical end | 48,136,192 (`0x02DE8000`) |
| Segment count | 1, wholly inside `0A` |

Independent `cmp` checks returned success for both the complete prefix before
`0x02D7D800` and the complete suffix after `0x02DE8000` in every changed build.
Thus the only physical differences in each 1,140,850,688-byte `0A` are inside
the one fixed ROST allocation. The archive directory was not rewritten and no
entry boundary, block count, size-block field, pack mapping, or sibling asset
moved.

This rules out outer-table corruption, a cross-pack replacement, an incorrect
physical offset, or archive misalignment as the immediate defect.

## Retail IFF/H7A structure

The retail entry is a one-block, one-file Visual Concepts IFF:

| Property | Retail value |
| --- | --- |
| IFF magic | `0xFF3BEF94` |
| IFF header size / H7A start | 84 bytes (`0x54`) |
| IFF file length | 435,329 (`0x6A481`) |
| Block count / inner-file count | 1 / 1 |
| Inner file | `roster` / `ROST` |
| Decoded part offset / length | 0 / 2,294,304 (`0x230220`) |
| Block hash / type hash | both `0xBB066001` |
| Block codec field | 7 |
| H7A shift | 10 |
| H7A stored length including wrapper | 435,245 |
| H7A payload length | 435,225 |
| Footer offset / size | 435,329 / 96 |
| Footer SHA-256 | `70f420d23342ac94ad3ce62f1acfe986f69f6b8c9a4461323b087f80d783a6d7` |
| Outer zero tail | 799 bytes |

The retail H7A payload consumes all 435,225 bytes with no trailing alignment
byte. It contains 284,015 tokens: 168,307 literals and 115,708 matches. Its
longest match is 66 bytes and its largest distance is 1,022, both legal for
shift 10.

## Rebuilt IFF/H7A comparison

| Build | H7A payload | Stored block | IFF file length | Footer offset | Zero tail |
| --- | ---: | ---: | ---: | ---: | ---: |
| Retail | 435,225 | 435,245 | 435,329 | 435,329 | 799 |
| Combined | 434,274 | 434,294 | 434,378 | 434,378 | 1,750 |
| Team only | 434,269 | 434,289 | 434,373 | 434,373 | 1,755 |
| Player only | 434,269 | 434,289 | 434,373 | 434,373 | 1,755 |

Every rebuilt entry has:

- the same 84-byte header size;
- the same block/file counts and one-based IFF pointer-table relationships;
- the same block hashes, codec 7, decoded length, block start, indexed flag, and
  H7A shift 10;
- a wrapper stored length equal to the block-table stored length;
- a bit-exact 96-byte footer, relocated as a complete unit to the new declared
  file end;
- only zero bytes after that footer; and
- no parser warning, bounds violation, gap, overlap, or footer pointer failure.

Before the compressed payload, the only changed scalar fields are the three
copies of the compressed/file length:

| Entry-relative field | Purpose | Actual changed byte positions |
| --- | --- | --- |
| `0x08` big-endian u32 | IFF file length | `0x0A..0x0B` |
| `0x38` big-endian u32 | Block stored length | `0x3A..0x3B` |
| `0x5C` big-endian u32 | H7A wrapper stored length | `0x5E..0x5F` |

All other IFF header and wrapper fields are bit-exact. The retail file length is
already odd (`0x6A481`), as are the team/player rebuilt lengths (`0x6A0C5`), so
the rebuilt files do not introduce a new internal alignment class. Only the
outer entry itself is 2,048-byte aligned, and that allocation is unchanged.

The footer payload uses its own self-relative pointers. Because its 96 bytes are
copied as a unit, relocation does not change any of its internal relationships.
Nevertheless, a ROST-specific loader could still have an unmodeled fixed-offset
or integrity assumption; that is explicitly isolated by the padded candidate
below.

## Decoded roster and relative-pointer comparison

The decoded retail body has SHA-256
`e959d3067ebcdbeb4f08979fa74d9fa61cf90fd91b90793863e6a3313be7f7ff`.
Its proved layout is:

| Region | Exact decoded range |
| --- | --- |
| Root plus table spans 0–22 (22 nonempty, one empty) | `0x000000..0x1F4794` |
| Reserved zero UTF-16 workspace | `0x1F4794..0x1F5734` (4,000 bytes) |
| String pool | `0x1F5734..0x230220` |

The two selected allocations are both wholly inside the string pool:

| Stable target | Decoded allocation | Size | Proved owner |
| --- | --- | ---: | --- |
| Pool 1,977 | `0x204CD4..0x204CE2` | 14 bytes | `player:788:last_name` |
| Pool 4,776 | `0x21C564..0x21C578` | 20 bytes | `team:0:display_name` |

The exact decoded differences are:

| Build | Changed decoded bytes | Difference positions |
| --- | ---: | --- |
| Player only | 6 | odd bytes `0x204CD5, 0x204CD7, …, 0x204CDF` |
| Team only | 9 | odd bytes `0x21C565, 0x21C567, …, 0x21C575` |
| Combined | 15 | the union of those two sets |

The even UTF-16BE high bytes stay zero because both source and replacement use
ordinary ASCII characters. No byte in the root, any player/team record, any
array, any pointer field, or the reserved workspace changes. Consequently:

- every stored one-based self-relative pointer remains bit-exact;
- every resolved target address remains identical;
- table counts, strides, record starts, memberships, and string target
  boundaries remain identical; and
- the independent semantic roster parser accepts all three decoded outputs.

This makes a decoded pointer-relocation defect unlikely. It does not rule out a
guest decoder producing bytes different from the project's decoder.

## The anomalous amplification

The generic re-encoder changes almost the whole compressed transport:

| Build | Decoded bytes changed | H7A payload bytes unequal at the same offset | Payload common prefix | Payload common suffix | Output token count |
| --- | ---: | ---: | ---: | ---: | ---: |
| Combined | 15 | 413,130 of 434,274 compared bytes | 9 | 0 | 282,878 |
| Team only | 9 | 412,821 of 434,269 compared bytes | 9 | 0 | 282,873 |
| Player only | 6 | 413,114 of 434,269 compared bytes | 9 | 0 | 282,873 |

In other words, a change near decoded offset `0x204CD4` or `0x21C564` causes
the compressed representation to diverge at payload offset 9, long before the
edited decoded region. About 94.9% of the compressed bytes at corresponding
offsets differ. The new stream is 951–956 bytes smaller and has about 1,142
fewer tokens than retail because it is a fresh greedy parse of the entire
2.29-MB body, not a local repair of the retail token stream.

The relevant implementation path is exact:

- `tools/apf_roster_identity_patch.py:462` calls
  `apf_texture_patch.compress_h7a(...)` for every non-no-op identity edit.
- `tools/apf_texture_patch.py:261` is a generic greedy encoder that builds a new
  match dictionary from decoded byte zero and retokenizes the complete input.
- `tools/apf_jersey_selector_patch.py:801` already implements
  `encode_preserving_h7a(...)` for this exact retail ROST.
- The selector writer actually uses that preservation-aware route at
  `tools/apf_jersey_selector_patch.py:1019`; the identity writer bypasses it.

That code-path mismatch is the most concrete defect found by this comparison.
It does not prove that the generic stream is syntactically illegal. It proves
that the current writer makes hundreds of thousands of unnecessary transport
changes and relies on the project's own decoder to validate them, precisely the
validation boundary that the runtime result falsified.

## In-memory token-preserving alternatives

The exact decoded outputs from the failed builds were re-encoded in memory with
the existing ROST token-preserving encoder. No output game was written. All
three candidates fit the fixed 436,024-byte payload ceiling, reparse with no IFF
warnings, decode to the intended body, retain the exact footer, and leave only a
zero tail.

| Candidate | Payload size | Delta from retail | Retail tokens preserved exactly | Split/replaced retail tokens | New file length | Zero tail |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Combined | 435,260 | +35 | 283,999 / 284,015 | 16 | 435,364 | 764 |
| Team only | 435,246 | +21 | 284,004 / 284,015 | 11 | 435,350 | 778 |
| Player only | 435,239 | +14 | 284,010 / 284,015 | 5 | 435,343 | 785 |

The verified in-memory outer-entry SHA-256 values are:

- combined: `17ef97ba27795c8a1a0060278d28aed4fcc985a58cd5dc603e516325f4fe5ce9`;
- team only: `cb38227effc8b1cd27452e1ed9b4e4df008fb0f915cfec0e3c6a59da2c4d0451`;
- player only: `04978a7310cf13b4261d843791b00ece513dd6ab56ed588d56109b8478eedd9b`.

These are not runtime-proved releases. They are bounded candidate transports
that reduce the number of semantically replaced retail H7A tokens from an
entire fresh stream to only 5, 11, or 16 affected tokens.

## In-memory exact-layout controls

A second candidate family isolates IFF/footer relocation from H7A tokenization.
The already-generated generic payload was padded with trailing zero compressed
bytes back to the retail payload length of 435,225. The original 84-byte header,
all three retail length fields, footer offset 435,329, footer bytes, and 799-byte
tail were then retained bit-exact.

The project decoder stops after producing the declared 2,294,304 bytes and
accepts the remaining zeros, so all three exact-layout candidates reparse and
decode exactly in memory:

| Candidate | Entry SHA-256 | Header exact | Footer plus tail exact | Decoded body exact |
| --- | --- | --- | --- | --- |
| Combined | `6516d1758f0323b002b94a10605ac6f48c5438b84b476fcf46e8f260071e9c22` | yes | yes | yes |
| Team only | `36c91a483518d74cc697bb94ea617d391b87dfc4d2c8a16f3a794ce0d56c423c` | yes | yes | yes |
| Player only | `7aba78aff0d67b0033aa588a2a2fde9431c16738112ff28b01ad03e7b429f3b1` | yes | yes | yes |

These controls still contain the generic encoder's near-global retokenization;
they change only one variable relative to the failed transport: container
length and footer placement return to retail. They must not be exposed publicly
without a runtime spot check because the guest decoder's treatment of trailing
compressed zeros is not yet observed.

## Most likely defect and remaining alternatives

### Most likely

**The roster identity writer is using the wrong H7A encoding strategy for this
runtime-sensitive ROST block.** The generic greedy stream is self-consistent
with the project's decoder but differs essentially everywhere from the retail
stream. The crash address looks like a malformed runtime pointer, which is
consistent with—though does not prove—the guest decoder or subsequent consumer
seeing bytes different from the offline output. The repository's existing
ROST-specific preservation path makes a much smaller, already bounded
alternative available.

### Still possible

1. **ROST loader assumes the retail compressed/file length or footer offset.**
   Other IFF writers may tolerate footer relocation, but this particular loader
   could have a fixed or cached size. The exact-layout padded candidates isolate
   this without changing semantic content.
2. **Unmodeled ROST integrity ownership.** A checksum or content signature may
   be outside the parsed IFF/ROST structures or computed by the XEX. No checksum
   field was observed changing here, but absence from the current parser is not
   proof of absence.
3. **A guest-only post-decode relocation/initialization rule.** All stored
   pointers and decoded addresses are exact offline, but the runtime may build
   secondary pointer graphs that depend on an unmodeled invariant.
4. **The fixed-allocation string writer violates an unmodeled string-pool rule.**
   This is less likely because the same-length team-only edit crashes exactly
   like the shorter player edit; the failure is therefore not explained by the
   player's additional zero padding alone.

Outer archive corruption, sibling-byte damage, decoded pointer damage, a wrong
entry index, footer byte corruption, and nonzero tail data are contradicted by
the exact comparisons above.

## Exact next experiment

Run only two new single-edit runtime controls, both as separate copied games:

1. **Team-only token-preserving candidate.** This changes the fewest relevant
   retail H7A semantics while still moving the footer by only 21 bytes. If it
   boots, the generic whole-stream encoder is causal enough to replace.
2. **Team-only padded-generic exact-layout candidate.** This retains the failed
   generic token stream but restores the retail IFF header, compressed length,
   footer position, and tail. If this boots while the first does not, prioritize
   the ROST fixed-layout assumption rather than token choice.

Interpret the matrix as follows:

| Token-preserving | Exact-layout generic | Classification |
| --- | --- | --- |
| Boots | Crashes | Whole-stream retokenization / decoder compatibility is the leading cause. |
| Crashes | Boots | File-length or footer-placement assumption is the leading cause. |
| Boots | Boots | Both changes avoid the failing transport; prefer token-preserving and then isolate further. |
| Crashes | Crashes | Trace guest execution at `0x84AB1D40`; integrity or post-decode initialization becomes the leading lane. |

Do not re-enable roster Replace or Build from this offline result alone. One
bounded changed ROST must boot and visibly consume its intended name before the
capability status changes.
