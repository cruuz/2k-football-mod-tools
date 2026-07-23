# NFL 2K5 streaming-audio origin gate: hostile review

Date: 2026-07-20  
Review target: `nfl2k5_ausb_fixed_slots.py` SHA-256
`49c4391884b2e3ed5a3928ab7b85316c2194213cae2892cae769ea807a2e1259`  
Disposition: **HOLD UI/build unlock until the final-build origin gate and the
complete private fingerprint inventory pass the acceptance matrix below.**

This review is about preventing a shareable `.2k5mod` project from becoming an
export route for audio decoded from the user's retail game. It is not a claim
that hashes can determine whether arbitrary transformed audio is copyrighted or
that Mod Studio can prove authorship.

## What is already sound

The new fixed-slot adapter correctly canonicalizes the 53,571 semantic AUSB
ranges into 53,570 physical slots, represents the one two-owner `cwdloop`
alias once, maps a slot across an archive seam in payload order, and refuses
non-identical overlaps. Its strict WAV parser fixes channels, 22,050 Hz,
frame count, chunk order, and allocation. Encoding is block-streamed and a
failure or cancellation truncates its caller-owned output to zero. The seam
projection test now rejects reversed, duplicated, overlapping, and same-size
wrong-offset segment maps.

Those properties make it a suitable codec/write-plan primitive. They do not
authenticate a source, reject retail-derived PCM, manage a project, or write an
XISO. The module says this explicitly and should remain locked behind a product
adapter until the following blockers close.

## Release blockers found

### P0: a fresh source cache leaves almost all streaming PCM unprotected

`Nfl2k5AudioService.validate_user_replacement()` rejects every standalone PCM
hash listed in the shipped AUDO catalog, but it checks AUSB PCM only when that
range already has a Play/Export-created private WAV sidecar. A fresh cache has
no such sidecars, so source AUSB range A can be supplied to an editable target
and pass this check. Playing the source range first changes the result. A
security decision must not depend on preview history.

Acceptance: before Replace, project load, project save, modified preview, or
Build can accept any audio edit, one complete private inventory must cover all
850 standalone AUDO occurrences and all 53,570 canonical AUSB physical slots.
The inventory must be a union: a source cue from either family is forbidden in
every editable audio target, including Menu Back.

### P0: the final backend can bypass the session gate

The build service accepts either a `StudioSession` or an existing canonical
provider JSON. `tools/nfl2k5_visual_mod_project.py` parses and encodes Menu Back
and standalone WAVs directly. It checks strict shape and later refuses a
replacement that is byte-identical to the selected encoded target, but it does
not call the PCM source-origin gate. A hand-authored canonical JSON therefore
bypasses the GUI/session check. The legacy Menu Back recipe/provider has the
same shape-only boundary.

Acceptance: the source-origin decision runs again inside the final backend/build
authorization boundary for `menu_back_audio`, `audo_audio`, and the future
`ausb_audio` kind. It must consume the same safely opened candidate bytes that
are encoded. Session validation is useful feedback, not authority. A raw
canonical JSON, a loaded `.2k5mod`, recovery state, batch import, and the legacy
Menu Back route must all reach the same final gate.

### P0: whole-file hashes alone permit trims, padding, and concatenation

A complete PCM SHA-256 catches a direct copy and a differently constructed WAV
containing identical PCM. It does not catch a middle excerpt of a longer source
cue, a shorter cue padded to a larger target, two source excerpts joined
together, or an otherwise exact copy with a small edit outside the copied
portion. Fixed frame counts do not prevent these attacks because the attacker
can choose or compose material to the target's exact length.

Acceptance: retain full-PCM hashes and add an exact long-window containment
gate. A practical deterministic contract is:

1. Canonicalize input to interleaved PCM16LE frames; key every index by channel
   count and sample rate.
2. Fingerprint one-second source windows at a quarter-second source stride,
   never crossing a cue boundary. Scan every candidate frame position with a
   rolling checksum and confirm a hit with SHA-256. This guarantees detection
   of an unmodified copied run of at least `window + stride - 1` frames even if
   the excerpt is shifted by an arbitrary number of frames.
3. Also retain the full hash for every source cue as inventory evidence. Apply
   the same silence classification before using a whole-cue hash as a refusal.
   For source cues shorter than the long window, index the complete non-silent
   cue as a variable-length window so padding it into a larger candidate is
   still rejected.
4. Exempt only deterministic low-information silence from both whole-cue and
   window refusal sets: all-zero PCM, or a
   separately specified near-zero constant/noise rule with both a peak and RMS
   ceiling. Duplicate frequency alone is not a silence exemption. Quiet,
   nonconstant speech or music remains protected.
5. Report only that exact source PCM or an exact long source window was found.
   Do not claim detection of gain changes, resampling, filtering, time stretch,
   or an attacker changing at least one frame inside every indexed window. A
   perceptual/fuzzy matcher can be a later defense, but is not safe to improvise
   as a release gate without a measured false-positive corpus.

The proposed one-second/quarter-second values are a default to benchmark, not
an invisible policy choice. If product UX requires another threshold, record it
in the private-inventory schema and show the exact protected duration in docs.

### P0: strict "no fingerprints in releases" conflicts with RC9 today

The sealed product currently allowlists
`reports/assets/nfl2k5_audo_import_capacity.json`. That file contains hundreds
of source `decoded_pcm_sha256`, `payload_sha256`, resource, wrapper, system, and
tail hashes; the audit found 905 `decoded_pcm_sha256` and 903
`payload_sha256` key occurrences. The release checker explicitly treats this as
reviewed metadata. It contains no retail payload bytes, but it is not truthful
to say that public releases contain zero source-audio fingerprints.

Acceptance requires one explicit product decision:

- Strict interpretation: split the public AUDO shape/ownership catalog from
  every source-content hash and generate the hash companion in the private,
  source-bound cache. The final backend can rely on the globally authenticated
  source XISO plus private derived metadata rather than shipping per-cue
  fingerprints.
- Narrow interpretation: declare the existing 850-row hash catalog a reviewed
  legacy metadata exception, while prohibiting the new 53,570-row PCM/window
  inventory from projects and releases. Documentation must say this rather
  than claim "no fingerprints."

The strict interpretation is the only one satisfying the literal requirement.
No new fingerprint inventory should be added to the release allowlist under
either interpretation.

### P1: project archive bounds are not yet AUSB-scale hostile-input bounds

The ZIP loader limits each WAV to 32 MiB and permits up to 100,000 audio edits,
but it does not reject an excessive aggregate uncompressed size before reading
members. That admits a multi-terabyte declared expansion even though the input
ZIP itself is capped. It also stages audio before the source-origin service is
called, although session state remains unchanged until later validation.

Acceptance: validate the full member table first, cap the aggregate declared
uncompressed bytes and simultaneous audio-edit count to a documented product
limit, check free space, then stage. One individually editable row does not
require supporting all 53,570 replacements in one project. The UI and docs must
state the simultaneous-edit cap. Project save should use the existing stable
single-link descriptor reader rather than `lstat()` followed by `read_bytes()`.

## Required private inventory contract

The inventory is complete only if all of these conditions hold:

- It is bound to the exact supported source XISO SHA-256, source size, catalog
  schema, canonical decoder revision/hash, and window-policy revision. A
  decoder or policy change invalidates and rebuilds it.
- Its row-ID set equals the catalog's full set, not merely the expected count:
  850 standalone IDs plus 53,570 canonical streaming IDs. Missing one ID and
  duplicating another must fail. The semantic AUSB owner count is 53,571; the
  one shared physical slot retains both owner IDs for a private diagnostic.
- Each row binds ID, channels, sample rate, frame count, complete PCM digest,
  and its long-window records. Equal-content cues may share digest storage, but
  coverage and occurrence counts remain independently checkable.
- The four cross-pack ranges are read by concatenating their exact ordered
  physical spans before codec validation/decoding. No fingerprint window may
  cross from one logical range into the next.
- Any malformed IMA block, changed source span, missing pack, cancellation, or
  count/shape mismatch aborts the whole scan. There is no partial-valid mode.
- Only digests, shape, private logical ownership, aggregate counts, and policy
  metadata survive. Raw encoded audio, PCM, WAVs, RIFF headers, preimages, or
  absolute host paths never enter the inventory.

The cache should live below the source-SHA-specific private cache in a named
forbidden subtree such as `derived/audio-origin-v1/`, with directory mode 0700
and files mode 0600. Its schema must never be accepted from a project or a
release tree.

## Aliases and public project identity

`cwdloop` has two semantic descriptor owners of one physical range. Internally,
both IDs must resolve to one edit ledger, one source fingerprint, one encoder
result, and one set of physical writes. Replacing either owner modifies/badges
both. Supplying both owners with identical authored WAV bytes deduplicates;
supplying divergent bytes fails before any edit is applied.

A public project should store one stable semantic asset ID and the authored WAV
only. It must not store the current `canonical_id` string because that string
encodes external-entry/range coordinates, physical spans, alias-owner lists,
source fingerprints, source paths, or rollback preimages. The destination
installation resolves and canonicalizes the semantic ID against its own
authenticated source.

## TOCTOU, cancellation, and publication criteria

Candidate origin checking and encoding must share bytes, not merely a pathname:
read the single-link non-symlink WAV through one pinned descriptor, validate and
fingerprint it, copy/spool it into an owned private temporary, then encode that
same verified copy. Recheck device, inode, size, mtime, ctime, link count, and
content digest before commit. Reopening the user's original pathname after the
origin verdict is not sufficient.

Source pack descriptors and the source XISO must remain read-only and pinned
during inventory generation and Build. The current source-cache loader checks
most extracted packs by size only, so a scanner must not treat a cache marker
plus sizes as source authentication. Either compare the consumed pack bytes to
the already authenticated XISO extents or use an equally strong source-bound
pack-integrity route. Recheck descriptor/path identity after the scan.

Inventory creation must use an owned O_EXCL temporary, fsync content, validate
its complete structure and digest, atomically publish, fsync the parent, and
re-stat the destination name. Cancellation or any callback exception removes
only the owned temporary inode and preserves an earlier valid inventory. Build
encoding similarly happens before the copied XISO is published; no logical
cross-pack edit may leave only one span applied.

## Adversarial test matrix required for GO

### Source-origin behavior

- Exact selected cue, exact different AUDO cue, exact AUSB cue in an AUDO
  target, and exact AUDO cue in an AUSB target are rejected at final Build.
  The interactive exact-selected-cue action may become Revert, but a loaded or
  raw project may not use that shortcut.
- A separately constructed canonical WAV with identical PCM is rejected.
  Strictly invalid RIFF containers fail earlier with a format error.
- Middle trim, source-with-leading/trailing-silence padding, concatenated
  source excerpts, and a one-sample mutation outside an otherwise exact long
  window are rejected by containment fingerprints.
- An authored candidate containing a long all-zero window is accepted. A quiet
  but nonconstant source window is rejected. Tests pin the exact silence rule.
- A transformed source copy that the exact-window policy cannot detect is
  documented as outside the claim; tests must not imply fuzzy detection.

### Coverage and topology

- A complete synthetic inventory validates; wrong source SHA, decoder hash,
  window policy, row count, duplicate ID, missing ID, wrong shape, malformed
  digest, or extra field fails closed.
- Both `cwdloop` owner IDs resolve one fingerprint/edit. Equal replacements
  deduplicate and divergent replacements fail transactionally.
- A synthetic range split after 50 bytes across two packs fingerprints and
  encodes identically to its contiguous form. Reversed, duplicate, overlapping,
  gapped, same-total wrong-offset, and pack-name/ordinal swaps fail.

### Boundary and race attacks

- A manually authored canonical provider JSON containing source PCM is refused
  by Build before an output XISO is created. Repeat for legacy Menu Back,
  standalone AUDO, and AUSB.
- Mutating/replacing the candidate WAV after session validation, after project
  load, and during Build fails. Mutating a source pack, inventory file, or
  alias map during scan/use fails, including same-inode/same-size mutation with
  restored mtime; ctime/content authentication must catch it.
- Cancel before the first range, after a normal range, during a cross-pack
  range, during window-table publication, and during encoding. No partial
  inventory, hidden WAV, encoded payload, project, or published XISO remains;
  a previous valid inventory remains usable.
- A ZIP with safe individual WAV sizes but excessive aggregate declared size
  is refused before extraction. Duplicate members, undeclared members, aliases,
  and over-limit simultaneous edits are refused.

### No-leak checks

- A saved `.2k5mod` contains only `project.json` and declared authored
  replacement files. Its strict manifest fields contain no source PCM/window
  hash, source owner list, physical coordinate/span, source path, original WAV,
  encoded preimage, or rollback data.
- Project load repeats complete origin checks before applying the first edit.
  Save and recovery repeat them; no cached boolean verdict is trusted.
- The release checker has a canary test that refuses any generated audio-origin
  inventory/value file even if a future allowlist names it. The staged release
  and deterministic archive are scanned for the private inventory schema/path
  and generated fingerprint values. Product code may name the schema and field
  protocol; generated values may not ship.

## GO definition

Streaming replacement can change from Export-only to Editable only after the
complete inventory exists on a fresh cache, the final Build boundary rejects
the full matrix, both alias owners behave as one edit, the four real cross-pack
slots compile as multi-span transactions, cancellation leaves no publication,
and the release/project no-leak checks pass. Until then, keeping the writer as
an isolated source slice is the correct product state.
