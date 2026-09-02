# NFL 2K3 / NFL 2K4 source compatibility boundary

The editor can identify an original-Xbox disc or loose `default.xbe` from its
XBE certificate, including an unsupported NFL 2K3 or NFL 2K4 source. That is a
read-only source-loading capability, not write authorization.

The available workspace contains no NFL 2K3 or NFL 2K4 disc image, loose XBE,
`vc_<title-id>` archive, or extracted pack. Consequently there is no
source-owned evidence for any earlier-title package index, chunk selector,
texture descriptor, fixed compressed allocation, roster table, or output
reopen. A 2K5 TXTR parser accepting a FourCC or Xbox pixel format does not show
that the same logical asset occupies the same package or byte span in another
game.

The current guardrail is intentional:

- `SourceInspector.disc_title` names an XBE/XISO from the certificate even when
  its whole-file hash has never been seen.
- `recognized` remains false unless a game/revision-specific contained
  executable fingerprint is pinned.
- the unified 2K5 provider additionally requires detected game `nfl2k5`,
  fingerprint `nfl2k5-usa-retail-xiso`, and the exact inspected source path;
  naming or spoofing an earlier title cannot reach a writer.
- every composed texture edit then verifies its owning pack and retail span.

Genuine earlier-title support needs, separately for 2K3 and 2K4:

1. A user-owned source disc or complete extraction, with `default.xbe` size and
   SHA-256 recorded as the contained revision identity.
2. A clean archive inventory proving root/packs, package indices, chunk names,
   formats, dimensions, compression bounds, and physical span ownership.
3. A semantic comparison that marks only truly shared targets; matching names
   or formats alone are insufficient.
4. Game-specific catalog/provider IDs and source guardrails. A 2K5 project must
   never be accepted as a 2K3/2K4 project or vice versa.
5. Copy-only writers, fixed-span round trips, independent output reopen/diff,
   retail-free packaging tests, and a headless build proof for each revision.

Until both sources exist, implementing edit/build would mean guessing the very
ownership information that protects user discs. The honest next input is the
2K3 and/or 2K4 Xbox source, not a relaxed hash or reused 2K5 offset.
