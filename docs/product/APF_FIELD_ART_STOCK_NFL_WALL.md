# APF Field Art — stock NFL vs focused editor (wall + path)

## User report

Field art appears for created-team workflows, but stock NFL endzone / field
assets seem missing from the dedicated Field Art editor even though they show
under All Textures.

## What is true in product code

1. **Inventory (browse/export):** `build_field_art_inventory` exposes **258**
   Field Art rows including **≈118 endzone_l0** and **117 endzone_l1** package
   pairs (stock NFL package-local art). These appear in the Field Art inventory
   browser and All Textures under the field-art category filter.
2. **Focused editor (writable):** `FIELD_ART_COVERED_TARGETS` offers only the
   **six** slots with offline-proved writers in `tools/apf_field_art_patch.py`
   (shared endzone layers outer 6, practice overlays outer 659, base divots
   outer 53). That is intentional honesty, not a missing catalog filter bug.
3. **Created teams:** custom-team appearance / user slots may surface different
   authoring paths; stock endzones remain package-local TXTR pairs until a
   per-package writer is proved.

## Unblock path

1. Pin one stock team endzone package (outer index + l0/l1) with retail SHA pins.
2. Extend `apf_field_art_patch` (or a sibling) to that package with independent
   volume verifier.
3. Expand `FIELD_ART_COVERED_TARGETS` only after the gate is green.
4. Label per-team vs shared ownership in the UI (already partial via inventory
   package groups).

## Status

Wall documented 2026-08-07. Focused panel copy now states stock endzones live
in the inventory browser; no overclaim of per-team Editable endzone writes.
