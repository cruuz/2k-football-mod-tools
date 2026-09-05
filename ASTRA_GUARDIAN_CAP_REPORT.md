# Guardian cap route B, 2026-09-05

**EXPERIMENTAL / UNWITNESSED.** Built the data-only C-family replacement and
one neutral quilt repaint through the existing import codecs. Both model
LODs fit their original spans. All three wrappers remain byte-identical;
archive growth is zero. No executable or roster record changes are involved.

> Every player wearing helmet C shows a guardian cap. Helmet C's normal look is replaced while this is on.

That is the required UI description of the intended effect, not a claim of
a played witness. This replaces the shared C geometry for all C wearers.
The selected test artwork is **Detroit current away, `09A0.IFF`,
`09A0:helmet02`**, catalog asset
`nfl2k5.uniform.09a0.helmet.helmet02`. Other uniforms retain their own artwork
on the enlarged C shell. Standard/A remains stock. There is no independent
cap selection or practice override in route B.

## What was built

- `mod_editor/core/nfl2k5_guardian_cap.py`: deterministic C-shell sculpt,
  neutral quilt artwork, whole-resource `status`/`apply`, atomic in-memory
  staging of the complete three-resource set, extracted-archive reader,
  XDVDFS-aware image status/build-copy resource pass, and a CLI producing
  fixed spans plus an exact receipt.
- `mod_editor/core/nfl2k5_models.py`: `ModelSpanSource`, an in-memory
  SCNE adapter using the existing parser/exporter and `compile_import`,
  without requiring a private resource inventory or filesystem archive.
- `mod_editor/core/nfl2k5_p8_texture_writer.py`:
  `compile_live_helmet_span`, using the existing live-helmet descriptor
  contract, six-mip generator, bounded palette quantizer and fixed-span fill
  encoder. It preserves the 128 system bytes and every wrapper byte.
- Standalone `tests/mod_editor/test_nfl2k5_guardian_cap.py`, and
  `reports/guardian_cap_receipt.v1.json` containing compiler results,
  source/output hashes, exact changed-byte counts, vertex identities,
  padding/scratch checks, and mip hashes. No retail binary is committed.
- `WIRING.md` contains the protected BuildPlan/preset/dispatcher/status/UI/
  allowlist/runtime/capability changes. Earlier depth-lock instructions in
  that file are preserved. No protected product, GUI or release file changed.

The uniform equipment writer handles shared-index `TSET` palettes in chunks
4 through 10. The live helmet is a standalone `TXTR` in chunk 12, so that
writer is correctly bypassed. The existing uniform catalog already has the
`helmet02` selector; it needs no additional selector or duplicate target.

The first compile exports the complete model with IDs, primitives, UVs,
normals and skin. The sculpt changes only C-shell entries of its POSITION
accessor. `compile_import` runs with normals/UV/colour writes disabled and
range widening disabled. The generated glTF retains its original connectivity
and skin. An independent decoded-byte check rejects any result outside the
selected position lanes, before a resource is returned.

## PROVED byte and geometry results

Inputs were read from the supplied retail extraction and XISO. The
extracted spans equal the spans read through the XISO's actual file table.
Pack names are matched case-insensitively: retail XDVDFS stores `b`, while
the extracted pack is named `B`. XISO offsets below are evidence for this
disc, not hardcoded placement used by the image writer.

| Resource | Pack-relative offset | Retail XISO offset | Complete span | Decoded bytes |
|---|---:|---:|---:|---:|
| `lo_body`, `o3c113` | `0:0x1A0850` | `0x61540050` | 135,840 | 229,248 |
| `hi_head`, `o3c115` | `0:0x1F3110` | `0x61592910` | 270,368 | 461,696 |
| Detroit away `helmet02`, `o4002c12` | `B:0xF42D9B0` | `0x1194AD9B0` | 36,704 | 88,512 |

**PROVED:** model allocation total **406,208 bytes**, complete trial
**442,912 bytes**, growth **0 bytes**. No resource/outer table entries,
pack block counts, XDVDFS entries or XBE sections change.

| C shell | Material | Vertex IDs, inclusive | Changed decoded bytes | Min/mean/max movement, cm |
|---|---:|---|---:|---|
| Low LOD | 16 | 4349..4460 (112 vertices) | 536 | 0.271 / 1.854 / 2.644 |
| High LOD | 21 | 11022..11456 (435 vertices) | 2,276 | 0.258 / 1.903 / 2.748 |

**PROVED:** those IDs are referenced only by `HI_HELMET_C`; none is shared
with another material. The position bytes are six bytes per vertex at
decoded base `0x11CC0` low / `0x26780` high, stride 10. Every byte outside
those lanes is identical, including both shape range constants, four-byte
normal lanes, IDs/connectivity, UV streams, skin selectors/transform tables,
morph data, material records, facemasks, accessories and A/B/body/head
vertices. All 112/435 selected vertices move. Both means exceed 1.5 times
the earlier 8%-of-mean-radius probe, rather than merely repeating inflation.

The shared profile adds broad shallow panel lobes, a thicker crown and rear,
outward ear padding, front-opening taper, brow lift and an upward-rolled
lower edge. It depends on position, not potentially split seam normals, so
coincident seam vertices receive identical displacements. Per-LOD bounding
boxes normalize the design; centimetre padding stays comparable between LODs.
The crown rises 2.219/2.278 cm, rear extends 2.090/2.094 cm, and maximum
side extent grows about 1.87 cm at both LODs. The lowest shell Y is unchanged;
the front extends only 0.740/0.768 cm. These are measured geometry properties,
not proof of clearance against every visor, strap, head or animation.

**PROVED:** the low/high compressed bodies consume 135,798 / 270,328 bytes
inside 135,808 / 270,336-byte stored bodies, respectively. The original
16-byte scratch words are retained, with the exact alias-scratch requirement
checked and recorded. Near-full encoded sizes are fill-encoder output and
are not an allocation of spare capacity.

**PROVED:** the repaint contains opaque, neutral gray 32-pixel quilt cells,
RGB 109..133, with darker seams and diffuse panel shading. All six P8 mips
(256, 128, 64, 32, 16, 8 square) are generated, swizzled and decoded back.
The base mip exactly equals the generated artwork; no base-image palette
loss occurs. Texture name, descriptor, dimensions, 87,360 index bytes and
1,024 palette bytes retain their allocation. The compressed texture is
filled to 36,669 bytes in its 36,672-byte body, with three padding bytes.
Its original 128-byte scratch word remains unchanged; exact minimum scratch
for the rebuilt stream is zero.

The stored resource hashes below include wrapper and compressed tail bytes:

| Resource | Retail SHA-256 | Applied SHA-256 |
|---|---|---|
| `o3c113` | `e3f71e2b930707d68eecfc9c1fa8025da6f1d1ec2087ec3d6ebaa3fa5fec604c` | `54b80cb326a5983fc58617430307435478029ac6d501ba3c9f49889824f4f4db` |
| `o3c115` | `4493cfafede437da6af7ddadfaa172bed3bd674a62801b73af3a99fc66315e43` | `289659a0590b9b1af3f53e0cfa9f01a5842bbd35c52ef8a52e52dfcdef67eccc` |
| `o4002c12` | `c3ae19fb03e006dc50bd5ad6c2a995d333cefe1448fb8902df123c073cc5ac4e` | `9a5479267fe8cbcac6176d62d817e67e949c79b82065d69a418fb80cdf0a843f` |

## API, artifacts and refusal behavior

```python
from mod_editor.core import nfl2k5_guardian_cap as cap

cap.status(span)                         # complete SCNE or TXTR, including wrapper
patched_span, receipt = cap.apply(span)  # optional key="o3c113" pins the identity too

resources = cap.read_archive_resources(pack0_path)
cap.resources_status(resources)
patched_resources, receipt = cap.apply_resources(resources)

cap.image_status(image_path)
receipt = cap.apply_to_image(private_build_copy_path)
```

**PROVED:** recognized retail becomes the pinned profile; already-applied
bytes return unchanged without recompiling or reading a source archive.
Whole-resource hashes refuse edits to wrappers, compressed tails, sibling
meshes or texture data. The grouped API requires exactly all three keys
and refuses every mixed retail/applied combination before compilation.
It never completes a partial install by silently guessing its intent.
Existing independent model or selected-helmet edits conflict deliberately.
Unrelated resource edits can compose because whole packs are not hash gated.

The image adapter locates the packs from XDVDFS, checks size/overlap bounds,
stages all three results, then rereads both placement and source spans before
the first write. It checks write lengths, fsyncs, reads back and verifies
unchanged image size. Idempotent application performs no resource writes.
Its descriptor closes even when validation or writes raise. Windows binary
open flags and resolved temporary paths are used. A build must discard an
incomplete private copy on I/O failure; this API does not promise a
power-loss-atomic multi-span transaction or lock out another writing process.

The end-to-end CLI was run successfully:

```sh
python3 -m mod_editor.core.nfl2k5_guardian_cap \
  --index '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --output .scratch/guardian/final-witness
```

That local directory contains `o3c113.span`, `o3c115.span`, `o4002c12.span`,
`detroit-away-cap.png`, and `receipt.json`. These private resource spans are
not committed. The committed receipt is copied from that actual CLI run.
No complete modified XISO was produced, and no source archive/image was
written. The usable build-copy pass is supplied for Claude's protected build
wiring; this branch does not expose an unwired GUI toggle.

## Tests and results

Commands ran headlessly with plain Python/unittest, without network, a
game/console/instruction emulator, GUI display or audio:

| Exact command | Result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_guardian_cap.py` | 18 tests pass, including real low/high compiler runs and retail XISO extent comparison; no evidence skips here |
| `python3 tests/mod_editor/test_nfl2k5_models.py` | 37 tests run: 26 pass, 11 skipped because this worktree lacks `reports/assets/nfl2k5_resource_chunks_v2.json`; the new cap tests directly exercise both real scenes without that inventory |
| CLI command above | Success; three resources, zero growth, output hashes match the earlier independent compiles |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | Existing failure in `PatchWriteTests.setUpClass`: depth locks refuse `unknown bench promotion call sites`; four section-table tests pass |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | Existing failure in `CaveReferenceTests.setUpClass` for the same depth-lock reason; no test methods reached |

**PROVED baseline failure:** both XBE commands were repeated from a fresh
`git archive HEAD` extracted into `.scratch/guardian/baseline`. HEAD is
`e6784e70f185567899b4256a4b8ef492dd96c7dd`. Both reproduce the identical
failure without any guardian-cap file or edit. Logs are under
`.scratch/guardian/`, including `baseline-memory-tests.log` and
`baseline-cave-tests.log`. They are not green, and this report does not claim
otherwise. Fixing that unrelated executable stack would exceed the brief's
ownership boundaries; `WIRING.md` calls it out for integration. This feature
has no XBE apply to insert in their executable-only composition.

The new tests cover wrapper/length/decoded-byte isolation, both real LODs,
movement and lower-opening bounds, six neutral mips, source and applied
hashes, all six partial-install combinations, tampering in all three
resources, idempotence, relocated/case-insensitive pack lookup, whole-copy
byte isolation, pre-write race detection, foreign-last-resource refusal,
short writes and handle closure. No fixture mocks the real scene or texture
compilers; those run once per retail test class. Image-write tests reuse those
verified compiled bytes to exercise the file adapter independently.

## HYPOTHESIS and Noah's witness plan

Appearance, cap recognizability, LOD continuity, animation clearance and
matte rendering remain **HYPOTHESIS / UNWITNESSED**. The quilt raster has
no painted shine, but the retail material's reflection pointer and lighting
updates are untouched. A gray image cannot prove matte game rendering.
The shared `helmet02` repaint can recolor C accessories. Additional
sideline/cutscene scenes (`o346c116`, `o4248c81`) were not edited or claimed
to be covered. This adds no vertices or triangles, but there is no runtime
frame-pacing measurement.

Noah's first witness is research memo section 4, step 1, **practice first**:

1. Build disposable stock and guardian copies from the same source, with
   the same roster and settings. Use Detroit current away. Select a known
   Detroit test player (decision: **Roy Williams**, if present in the chosen
   roster) and set the existing Helmet choice to Revolution/C. Keep another
   C wearer and one Standard/A wearer on the field. Record actual player
   identity if a different roster requires a substitute.
2. Enter Free Practice/Scrimmage. Compare the same player, uniform and camera
   on the stock and guardian builds, first close-up, then at gameplay
   distance. Both C wearers should have the cover; the Standard/A wearer
   should remain stock. This trial does not put caps on all practice players.
3. View front, sides and rear. Inspect crown thickness, ear openings,
   forehead/visor edge, rear lip and chinstrap. Compare no/clear/dark visor
   and different C facemasks. Check the neutral cap reads as padded fabric,
   including whether accessories are recolored acceptably and whether shine
   is excessive. Decide and record acceptance or a specific required resculpt.
4. Walk the camera across LOD changes; inspect idle, snaps, head turns,
   catches, tackles and replays for clipping, floating, cracks or popping.
   Repeat with varied heads/body sizes, offense, defense and substitutions.
5. In exhibition on the same uniform, confirm C replacement still applies
   to every C wearer. Check Detroit home and another team's uniform to
   document enlarged geometry with their unchanged artwork. Inspect sideline
   and cutscene players separately, without assuming coverage.
6. Build from the original source with the trial disabled and verify the
   normal C appearance returns. Merely unchecking a flag while using an
   already-modified input does not restore resources. Keep screenshots/video,
   player/uniform/camera identities, cap receipt hashes and observed outcomes.

Only Noah's played results can turn those checks into a witnessed claim.

## Precise later route A specification

The following is a separate **HYPOTHESIS / implementation specification**
from the read-only hub memo `GUARDIAN_CAP_RESEARCH_2026-09-05.md`, section 3.
No addresses or roster bits are allocated by this branch.

1. **Geometry and draw contract.** Sculpt the existing B shell in the same
   two shared player scenes, keeping B IDs, topology, UVs and head skinning.
   Leave each player's normal A/C shell, A/C accessories, facemask, visor,
   logo, mouthpiece and number routes enabled. Enable only the B shell as
   the optional cap; do not enable a second complete player scene. B has
   120 low / 402 high referenced vertices and 92 / 280 emitted triangles.
   Extra shell workload at 22 capped players is 2,024 low / 6,160 high
   triangles, a topology budget rather than measured GPU cost. Existing
   vertex lanes occupy 2,880 / 6,432 bytes; reuse adds no vertex buffers or
   SCNE rows. Require coverage/clearance on both A and C before accepting it.
2. **Hook contract and allocator.** Pin the five retail bytes at VA
   **`0x0008F02E`: `8B 55 EC 8B C2`**, displaced instructions
   `mov edx,[ebp-0x14]; mov eax,edx`, and resume at **`0x0008F033`**.
   EBX is the roster record; EDI is the scene instance in this binder path.
   Preserve live registers/flags/stack, execute the displaced instructions
   exactly once, then resume. Budget **0.5 to 2 KiB of executable code** for
   decision/binding/fallback/lifecycle hooks, **336 bytes writable bitmap and
   header**, plus separately sized writable cache/lifetime state. These are
   estimates, not assembled sizes; persistence/matte hooks may exceed them.
   Use the later grown-section allocator with aligned, nonoverlapping,
   permission-correct code and data extents. No runtime data in `.text`.
   Do not convert an oracle `unknown`, retail reference, unreserved address
   or stale manifest result into free space. Regenerate the final-stack
   reservation manifest, reserve actual assembled spans, repin section
   digests, and compose the real route-A XBE patch into both safety suites.
3. **Decision and identity.** Store a separate `guardian_cap` property in
   project/roster metadata, independent of Helmet, Star and depth locks.
   A first fixed-roster trial may compile a source-pinned bitmap: 2,547
   records require 319 bitmap bytes; a 16-byte header and alignment make
   336 bytes. Specify primary 0..2478 followed by secondary 0..67. A candidate
   16-byte header is magic/version/count plus roster identity token and
   generation; validate the complete roster digest in the build receipt,
   and prove the live roster-generation/pointer-to-index mapping before use.
   Missing/mismatched metadata or out-of-range/non-player pointers leave
   the cap off. Index alone is not durable identity across saves, trades,
   clones/imports or generated rookies. Full franchise support requires
   a proved identity/preservation scheme, not just the initial bitmap.
   Do not use selector 2/3. Do not allocate `+0x52/+0x53`. Record `+0x0D
   bit 0` remains only an unaudited candidate, not owned storage.
4. **Practice policy.** In an active player context, unsigned game mode
   `0x00E5FF80` in 0..3 enables caps for everyone; in games, consult the
   individual property. Skip raw helmet selectors outside 0/1 and headless
   or non-player preview contexts. Confirm that the actual Free Practice
   entries reach these modes. Do not temporarily mutate persistent roster
   bits to implement practice. Invalidate/rebind on mode, roster, player,
   uniform and scene changes, including practice-to-exhibition transitions.
5. **Texture registration and archive budget.** The existing name-cache
   pair 2/3 is `helmet01`, and B name slots 3/4 already exist. The research
   found zero shipped `helmet01` TXTRs. A name/cache pointer alone is not
   a texture registration. Register a new global neutral `helmet01` TXTR
   in the already-loaded common player resource group, and prove load order,
   cache population (`0x0008E620`), lookup fallback (`0x0008E580`), ownership
   and release/reload lifetime before binding. At the existing P8 layout the
   budget is **88,512 decoded bytes** (128 system + **88,384 video/palette**),
   plus a **32-byte wrapper before compression** and actual aligned stored
   allocation. Do not assume the decoded size is an on-disc compressed size.
   Outer 3 ends at `0x316DE0`; the next outer begins at `0x317000`.
   The **544-byte gap is alignment padding, not a resource slot**.
   The current archive has 4,323 12-byte rows from pack 0 offset `0x9C`,
   with outer-3's row at `0xC0`. An insertion/growth path must update outer
   resource enumeration, lengths/offsets and pack block counts; if pack
   extents move, update XDVDFS and every affected placement. The fixed-span
   importer does not implement that allocator. A grown XBE section also
   does not by itself register an archive texture.
6. **Material and fallback contract.** Use the real B material helper
   `0x0008E3F0` to clear the disable bit at `+0x08` and bind the cap texture
   at `+0x30`. Reflection lives independently at `+0x34` through
   `0x0008E430`; later `0x0008FAD0` handling includes B and updates material
   byte `+9`. Prove cap-specific matte handling survives those updates,
   and restore normal instance state when disabled. Operate on the instance
   material table, not shared geometry/cache state that affects other
   players. If texture registration/lookup/lifetime fails, disable the B
   overlay and preserve the player's normal helmet. Test missing textures
   and every cache reload; never bind a stale pointer.
7. **Full-feature acceptance.** Practice first with mixed A/C and no flags;
   then two teammates with the same helmet/uniform and exactly one flagged
   in a game, repeated on A and C. Test all practice types, Basic Training,
   seven-on-seven if enabled, stars/depth locks, all visor choices, uniforms,
   substitutions and 22-player frame pacing. Test practice exit, save/reload,
   trade, clone/import, franchise advancement and generated rookies. Add
   explicit sideline/cutscene coverage or state its limitation. Keep the
   feature experimental until Noah witnesses appearance, selection, matte
   behavior, missing-texture fallback and persistence. Rosters/artwork GUI
   controls ship only when all these dependencies compile together.

## Scope and commit discipline

Worked only in `astra/r61b-guardian-cap` at the supplied worktree. The hub
memo, extraction, XISO and original Git objects were read-only inputs.
No other worktree, original project file, source game resource or release
tag was edited. No push, network, emulator, GUI display or audio was used.
`ASTRA_BRIEF.md` and `.scratch/` are excluded from the commit paths.

The explicit-path commit in the main worktree was refused because Git could
not create its `index.lock` on the read-only metadata filesystem. Following
the brief's authorized fallback, the seven deliverable files are committed
in an isolated repository at `.scratch/guardian/commit-repo` on the same
branch name, and exported as **`.scratch/guardian-cap.bundle`**, based on
`e6784e70f185567899b4256a4b8ef492dd96c7dd`. The worktree files remain in place.
The bundle contains the new commit, not the brief, scratch artifacts or any
retail resources. It is an incremental Git bundle and requires that base
commit when fetched. No push was attempted.
