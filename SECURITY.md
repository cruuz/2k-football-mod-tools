# Security policy

## Reporting a vulnerability

Please report privately rather than in a public issue: use
[**GitHub's private vulnerability reporting**](https://github.com/cruuz/2k-football-mod-tools/security/advisories/new)
on this repository.

Include what you did, what happened, and what you expected. A reproduction is
ideal but a clear description of the flawed reasoning is often enough — several
of the most valuable findings in this project were review conclusions, not
exploits.

## What counts as a vulnerability here

The usual categories apply, but this project has one of its own that matters
just as much:

**A guarantee that claims more than it enforces is a security bug.** These tools
tell users things like "your original is never modified", "this publish cannot
clobber an existing file", "this directory is private to you", or "these bytes
were verified before they were executed". If any of those statements is true on
one platform and merely *asserted* on another, that is a defect of the most
serious kind here, whether or not it is exploitable — because people decide what
to risk based on those sentences.

Concretely, reports are very welcome about:

- A fallback path (typically Windows or macOS) that reports success or a
  guarantee flag stronger than what it actually enforces.
- A check that can be defeated by a symlink, junction, reparse point, hardlink,
  or a rename between the check and the use.
- Anything that lets a write reach the user's **original** disc image or save.
- Any way retail game data could end up committed to the repository or inside a
  published release archive, which both release gates are meant to prevent.
- A published archive whose bytes do not match its `.sha256` sidecar, or which
  does not rebuild reproducibly from the recorded commit and epoch.

## Scope

In scope: this repository's code and its published release archives.

Out of scope: the games themselves, emulators, and anything requiring a
compromised machine to begin with. Bugs in the vendored
[extract-xiso](https://github.com/XboxDev/extract-xiso) source belong upstream,
though tell us too if a bundled binary is affected — the bundled builds are
pinned by exact size and SHA-256 and can be rebuilt from
`tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md`.

## What to expect

This is a small hobby project, not a funded one, so there is no bounty and no
guaranteed response time. What is promised is that a real finding gets fixed
rather than argued with, and that if a shipped guarantee turns out to be
overstated it gets **corrected in the documentation immediately**, before the
code fix lands. Precedent: beta 3 was published purely to correct shipped
documentation that no longer matched shipped behaviour.
