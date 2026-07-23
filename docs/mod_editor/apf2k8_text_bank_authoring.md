# APF 2K8 text-bank authoring

APF 2K8 Mod Studio recognizes all four archive resources explicitly typed as
`TXT loc system` or `STRG`. Together they provide 2,413 underlying string
allocations. 2,410 are editable; the two required localization fallbacks and
one zero-capacity empty STRG allocation are deliberately read-only.

## Editing rules

- The limit shown beside the editor is measured in UTF-16 code units. Ordinary
  letters normally use one unit; characters outside the Basic Multilingual
  Plane use two.
- NUL characters cannot be entered.
- A shared allocation may supply several labels. The displayed reference count
  tells you how many consumers change together.
- A replacement can be shorter than the original. It cannot exceed that one
  allocation's original capacity.
- Replace, individual Revert, Revert All, Undo, project save/load, and Build use
  the same provider as the rest of Mod Studio.

The project stores only your replacement text and logical asset identity. It
does not store the original string or any original game bytes. The built game
folder does contain data from your own copy and must not be shared; share the
`.apf2k8mod` project instead.

## Why a valid edit can still be refused at build time

The two STRG banks share compressed IFF blocks with other assets. Mod Studio
rebuilds all pointers and preserves the exact decoded allocation, then must fit
the recompressed block back into its fixed outer entry. Unusually
hard-to-compress replacement text can exceed that final compressed envelope
even when it is within the displayed character limit. In that case the build
stops safely, leaves the source unchanged, publishes no partial output, and
asks for shorter or simpler text.

## Text that is not part of these four banks

This feature does not reinterpret every printable byte as prose. Roster
identity, typed credit/event records, layout data, font/kerning resources, and
direct executable labels have different formats and remain in their own tool
categories. A row is read-only when its own format does not yet have a bounded
writer; it is never silently omitted or treated as STRG by guesswork.
