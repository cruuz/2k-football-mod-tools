# APF-4: independent live situation exclusions

## Control and scope

CPU Play Calling now has a separate **Live situations: exclusions and requested personnel** section. Enable the experimental switch explicitly, choose one of twelve buckets, and check formations to exclude. No preset stages or enables this option. The selected named book owns the mask; other books and other buckets retain their choices. Up to 48 named book profiles fit in version 1. Formations 0 through 150 are authorable; cached special formations keep their existing paths.

The older 23 situations remain representative queries. Openers, first-and-10 and sudden change can have identical selector inputs, so they cannot have separate semantics here. The new key is actual down 1 through 4 crossed with absolute single-precision longitudinal target-minus-ball distance: at most `f32(182.88)`, at most `f32(640.08)`, or above it. These correspond to two and seven yards in the native 91.44-unit scale. The exact floating coordinate difference determines boundary membership. Clock, score and field zone are deliberately not part of this key.

Only ordinary automatic offensive draws in scrimmage phase 4 use the policy. Defense, kick/try phases, special requested rows, cached special shortcuts and calls with an explicit formation or play bypass it. The key reads actual down at `[G+0x6C]+4` and coordinates at `+0x18` and `+0x28`. G is `851A2780` on BASE and `851A27B0` on TU 1.1. This requires no invented event label or requested-row RNG state.

## Persistent storage and native hooks

| Purpose | BASE | TU 1.1 |
| --- | --- | --- |
| Category draw hook; displaced `li r5,3` | `8486B198` | `8486BE98` |
| Formation draw hook; displaced `li r5,1` | `848696C0` | `8486A3C0` |
| Immutable policy allocation | `8462CA00..8462FFFF` | same |
| Executable allocation | `84D0E300..84D0EFFF` | same |
| Writable draw receipts | `852D6500..852D653F` | same |

The authored Xenia TOML overlays the exact pinned executable image, the framework used by the earlier pass-fetch experiment. It does not rewrite, sign or redistribute the encrypted retail XEX. Its policy directory lives in the final mapped string-section page beyond declared string contents. Code is beyond executable contents, and receipts are beyond declared data contents in the final mapped data page. Both image profiles are independently pinned. Arbitrary aligned words in compressed assets can numerically resemble these addresses; the audit records those untyped collisions separately. The audit checks section sizes and flags, zero padding, aligned executable address literals, direct executable branches and nearby `lis`/displacement references. This is not a claim about arbitrary computed addresses. The retained `.reloc` payload is opaque rather than decoded PE relocation blocks; untyped data-word collisions remain listed for review. The audit does not certify every possible data-derived pointer. The reservation manifest records ownership. Existing pass-fetch patch writes end before the new code, and pairwise write sets are disjoint.

Version 1 starts with four big-endian words: magic `APF4`, version 1, book count, and entry stride 268. Each sorted book entry has a NUL-padded 28-byte ASCII name followed by twelve 20-byte masks. Mask word `formation//32` uses bit `formation%32`. Only bits 0 through 150 are allowed; names, duplicate IDs, nonzero padding, trailing bytes and unsupported versions are rejected. Missing books, an empty profile directory and zero masks mean no exclusions. Runtime lookup compares the current SPLB UTF-16 name at `book+0x30` against the directory. Normalization cannot overwrite the separate policy block.

Two leaf hooks run after the original candidate enumeration and before its weighted lottery. They preserve candidate order and original weights, compact pointers and weights together, and consume no extra RNG calls. Formation filtering acts on the actual bounded native candidate buffer. Category filtering honors membership, retail primary preference, the hidden-formation flag and cached special exclusions. It conservatively keeps a category when an unexcluded structural member remains; the subsequent native formation enumeration retains authority over play-specific eligibility and its forty-slot bound. It does not recompute average rating weights.

If either filtered buffer is empty, that draw retains every original pointer, weight and count. Each active draw writes six unsigned big-endian words: live key, sorted book-directory ordinal, original count, filtered count, empty-draw flag, and cumulative fallback count. Category receipt starts at `852D6500`, formation receipt at `852D6518`. These are last-draw diagnostics; they are not a match log or a new guarantee about a retail book that was already invalid. A valid original draw remains valid when exclusions empty it.

## Requested rows and preview

The computed request is read-only: ordinary offense calculates it using down/distance, jitter, urgency and overtime field position. A bucket is not a constant requested row. The panel shows a representative midfield sample, its neutral request and its RNG endpoint range. **Preview this live situation** fills the existing custom preview and runs the same call preview with the bucket's mask. Preview receipts report category and formation fallback counts.

The stored MASTER category comparison row is editable beside the live situation, with an explicit **all books** label. This edits the data the game actually stores; it does not pretend to replace the computed request for one bucket. The requested eleven role slots are displayed. An empty TE depth list substitutes an FB, as APF-3 proved through the final native player provider. Requested TE counts are not a guarantee of TE players on the field.

Masks, their enable switch and stored-row edits use existing reviewed event receipts, undo, save/reload and conflict replay. Building exports both version-specific patches, `situation-masks.bin` and `situation-mask-receipt.json` beside the copied game. Explicit patch installation remains necessary. The page can export, review/install, check and remove the canonical situation patch. The launcher synchronizes it through the same validated launch-folder route as the other Studio patches. Disabling the project switch does not uninstall an already installed patch: remove it, or export/install the empty policy, then restart the game.

## Evidence boundaries and retest

**PROVED** means exact byte checks or bounded execution in the offline native suite. Both images execute the authored machine code against relocated MASTER data and native book enumeration. The existing 30-case native suite also runs with an empty mask through the two detours. Additional cases exercise local exclusions, other buckets/books, empty draws, live-key boundaries, special branches and exact patched image/data bytes. The native exact image regression pins the one-exclusion O-ManBlock fixture to BASE SHA-256 `de19823f326573ffd8a6279e79afc981a9003f304ad572d5aee1ed463df504a5` and TU SHA-256 `fb9edef7ddb700b95c6fa0f07dce530bf416e664d4dcdb4046d14fe831aa23aa`. Its data block SHA-256 is `ba2f34bcd2a76502f51a2e0e5103675a7b00e7601208c6c8b3e23270ffce0cca`. Full-width synthetic ABI execution independently checks GPR upper halves, CR, FPRs, FPSCR, LR/CTR, guarded writes and stack restoration.

The command ledger and receipts in `reports/b71_apf4/` record the actual commands, outcomes and counts; final delivery status is in `ASTRA_REPORT.md`.

**HYPOTHESIS / UNWITNESSED:** arbitrary live save/USER merge lifecycles, live loaded-book naming after every mode transition, rendered on-field outcomes and actual Xenia patch consumption need an in-game witness. No emulator is opened by this work. The native instrument supplies explicit RNG/history, field and roster state; it does not run a match scheduler.

1. Select O-ManBlock and explicitly enable situation exclusions. In third down, over seven yards, exclude formation 14, or all three Queens formations 2/14/24. Keep another ordinary formation available.
2. Preview third-and-8, third-and-3 and second-and-8. Save/reopen the project and verify only the selected bucket retains the checks. Undo and reapply one checkbox.
3. Build a copied game. Review the data and patch receipts and install only the patch matching BASE or TU 1.1. The canonical installer handles the filename and selected launch configuration.
4. The tester compares those downs/distances in game, recording executable profile, selected book, any USER/save overlay, requested personnel and actual players. Record whether a TE depth list is available. Repeat after changing teams/books.
5. For fallback, exclude every ordinary formation in one bucket. A valid original book must still call a play; inspect the native last-draw fields when debugging. Special kick and two-point paths should retain their original calls.
6. Remove the installed patch and restart to compare retail behavior. Reopening a project alone does not change the installed patch.
