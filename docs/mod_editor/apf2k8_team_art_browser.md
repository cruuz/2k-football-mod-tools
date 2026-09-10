# Team Art and the APF workspace theme

Open **Logos & Team Art → Team Art**, or **Browse Team Art** from Uniforms or Field Art. Load your own supported APF game. The browser lists all 118 crests, 118 endzones, 206 wordmarks, and 24 packages each of jerseys, shoulders, pants and digits. The complete grid appears before thumbnails finish. Background workers decode visible rows and one following row, then continue as you scroll or filter; unseen packages do not keep the application busy.

Choose a family, search a team label, entry number or package name, and select a thumbnail. The inspector gives the package, exact outer entry, semantic layer names, inner indices, dimensions and codec. Crest inspectors also show the linked Team Select logocache catalog index. Retail-team filtering uses proved built-in selector assignments; it deliberately excludes endzones whose retail selector ownership is not proved. Unassigned entries keep their numbers. Wordmarks also identify themselves visually.

**Replace…** opens a layer checklist. Choose or drop a PNG on each required layer. Crests require separate `logo_l0` and `logo_l1` files because their RGB channels encode six distinct region masks. Endzones require every layer the selected package actually owns (117 two-layer packages and one single-layer package). Wordmarks, jerseys, shoulders and pants use their single color layer. Digit packages show all 20 color/normal textures; you may replace a subset, and the combined staged digit set is checked against the shared package allocation before staging.

PNGs must have the displayed dimensions and satisfy the existing family's pixel contract. Successful staging is one Undo operation. **Revert package** removes that package's staged edits, also as one Undo operation. Save Project preserves authored art and recipes. **Build Game Folder** runs the existing writers, regenerated-mip checks, allocation checks and decode-back verifiers against a copied output. A staged image is not a promise that arbitrary artwork fits its compressed allocation. Changed art remains in-game **UNWITNESSED**.

The browser cache lives under `ApfAssetIO.originals_root / PREVIEW_CACHE_VERSION / team-art-v1`. Source identity, decoder version, package identity and staged-image hashes separate previews. Crest detail-layer hashes participate in cache identity. Invalid cached PNGs rebuild. These are private derived images, never repository or release content.

## Workspace controls

All 14 pages have compact summaries and a single-line capability strip. **Details** opens the complete cards, long guidance and research boundaries. The page action is mirrored in the header and a fixed footer so it remains reachable while scrolling an inspector. Long tables have alternating rows, natural header sorting and full-text hover tips. Sorting moves visual rows while retaining logical record identity, including embedded mapping controls.

**Ctrl+F** focuses the visible workspace search. **Escape** clears it. **Enter** on a selected list record transfers focus to its inspector. The private workspace store remembers window geometry, the last page and each page's selected workspace without changing recent-source or recovery records.

## Theme maintenance

`mod_editor/apf_studio/apf_theme.py` owns all UI colors. Install it once on `QApplication`, before constructing pages. Native Qt widgets, parentless dialogs, input/file dialogs, combo popups and menus inherit it. Platform-native file chooser chrome remains controlled by the operating system; the offscreen audit uses the Qt file chooser. No dialog-local stylesheet is needed. Use `primaryButton`, `secondaryButton`, `utilityButton`, or `dangerQuietButton` for the button hierarchy.

| Token | Purpose |
| --- | --- |
| canvas, surface | Window and panel backgrounds |
| base, alternate, raised | Data rows and controls |
| text, muted | Body and secondary text, including disabled states |
| accent, ink | Primary action background and readable foreground |
| selection | Selected rows |
| success, info, warning, danger | Consistent status vocabulary |
| border | Edges, separators and handles |

Game palette swatches and decoded art are data. They retain their source colors. Body text must achieve at least 4.5:1 contrast. `ui_audit.py` checks effective active, inactive and disabled palettes and explicit table-cell brushes. `test_apf_theme_layout_qt.py` walks all 14 pages, every dialog fixture, keyboard focus and 1366×768 bounds. `tools/apf_ui_snapshots.py --audit --source <retail-folder> --output <private-directory> --team-art-families` repeats the audit with live read-only retail metadata and captures every family. Add new dialogs to its fixture list.

`page_layout.py` supplies consistent spacing, wrapping toolbars, bounded tab stacks, visible empty-list Load controls, and the fixed action footer. Large dialogs use a scrollable body with their button box outside it. Intentional vertical content scrolling is permitted; horizontal page overflow is rejected. Use the screenshot receipts to review actual composition as well as the automated checks.
