# Colour & lighting project controls

Build contains 55 sliders, each with a switch that retains its authored value while Off. Each group has an independent switch. The master option stays Off in every preset; presets do not alter custom values. Broadcast (default) resets the controls to v2.1. Retail resets every group and lever to retail. Neither button changes the master option.

End zones / centre-logo greens and outside-grass colour follow turf by default. Unlink them to use their own stored hue, saturation and brightness. Painted non-green artwork is preserved. Outside brightness matching and edge shade remain separate controls. Divot contrast is the alpha of the low-frequency wear layer. Map contrast scales green value departures from the used-green mean; it changes mowing bands only when they already exist in that map, and cannot add stripes. Material turf has no map-contrast control.

Night and dome share the existing night_indoor table. Seven tables keep their retail directions, counts and shadows. White balance interpolates retail colours to the v2.1 broadcast colours. Gain multiplies all intensities; ambient, key and fill control their respective intensities. Fill sets the remaining light(s), which have equal intensities in these retail and v2.1 rigs.

## Prediction scope

The swatches all show the same selected class and condition using `predicted_on_screen`: colour map × (ambient colour × intensity + sum of light colour × intensity) × SCREEN_FACTOR. The beta-70 night capture is reproduced as (51, 61, 32). The v2.1 example (181, 216, 102) predicts (102, 122, 52) at night and (83, 99, 47) by day. This is a predicted mean, not a render: bump, divot coverage, tints, edge shade and stripe contrast are outside the model. Changing those controls does not move its swatch. Other stadium classes and conditions are extrapolations. All custom appearance remains UNWITNESSED.

| Class | Retail numeric reference | Broadcast target | Measurement |
|---|---|---|---|
| Outdoor grass (Arrowhead reference) | (100, 125, 66) | (107, 121, 53) | s13nd.iff colour-map median |
| Dome grass (Indianapolis reference) | (52, 90, 61) | (102, 125, 78) | s11dd.iff used colour-map mean, rounded |
| Material turf (Detroit reference) | (64, 96, 51) | (63, 85, 58) | s09dd.iff color_premipped material +0x18 |

Outdoor day uses the report target (88, 105, 61). The Indianapolis and Detroit targets are from the existing Week 1 table. Preview selectors are saved but do not change the writer settings digest. The material reference is its green +0x18 word; the +0x14 white word remains untouched.

## Controls and writer paths

All numeric controls below write through `mod_editor/core/nfl2k5_modern_color.py`. Switches and links are resolved by `control_value` / `surface_group`. Defaults preserve the existing retail/modern pins.

| Key / lever | Broadcast default | Range | Off value | Writer function |
|---|---:|---|---:|---|
| `turf.hue_target`: Broadcast hue (degrees) | 72 | 45–150, step 1 | 72 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `turf.hue_pull`: Hue pull | 0.5 | 0–1, step 0.01 | 0 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `turf.saturation`: Saturation | 1.12 | 0–2, step 0.01 | 1 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `turf.value_lift`: Brightness curve | 2.8 | 0.25–5, step 0.01 | 1 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `endzones.hue_target`: Broadcast hue (degrees) | 72 | 45–150, step 1 | 72 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `endzones.hue_pull`: Hue pull | 0.5 | 0–1, step 0.01 | 0 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `endzones.saturation`: Saturation | 1.12 | 0–2, step 0.01 | 1 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `endzones.value_lift`: Brightness curve | 2.8 | 0.25–5, step 0.01 | 1 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `outside.hue_target`: Broadcast hue (degrees) | 72 | 45–150, step 1 | 72 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `outside.hue_pull`: Hue pull | 0.5 | 0–1, step 0.01 | 0 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `outside.saturation`: Saturation | 1.12 | 0–2, step 0.01 | 1 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `outside.value_lift`: Brightness curve | 2.8 | 0.25–5, step 0.01 | 1 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `turf.map_contrast`: Map contrast / mowing stripes | 1 | 0–2, step 0.01 | 1 | `regrade_palette / regrade_colour_word → modern_field_scene` |
| `outside.match`: Match field brightness | 1 | 0–1, step 0.01 | 0 | `modern_field_scene` |
| `outside.falloff`: Edge shade strength | 0.45 | 0–1, step 0.01 | 1 | `modern_field_scene` |
| `divots.contrast`: Blotch / wear contrast | 0.3 | 0–1, step 0.01 | 1 | `regrade_palette → modern_divots_span` |
| `normal.flatten`: Bump flatten amount | 0.68 | 0–1, step 0.01 | 0 | `flatten_normal_palette → modern_normal_span` |
| `tints.day`: Day tint correction | 1 | 0–2, step 0.01 | 0 | `corrected_tint / corrected_tint_word → modern_field_scene / modern_bundle` |
| `tints.afternoon`: Afternoon tint correction | 1 | 0–2, step 0.01 | 0 | `corrected_tint / corrected_tint_word → modern_field_scene / modern_bundle` |
| `tints.night`: Night tint correction | 1 | 0–2, step 0.01 | 0 | `corrected_tint / corrected_tint_word → modern_field_scene / modern_bundle` |
| `rig_day.gain`: Overall gain | 1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_day.balance`: White balance (retail to broadcast) | 1 | 0–1, step 0.01 | 0 | `modern_table → apply` |
| `rig_day.ambient`: Ambient strength | 0.58 | 0–2, step 0.01 | 0.285 | `modern_table → apply` |
| `rig_day.key`: Key light strength | 1.2 | 0–2, step 0.01 | 1.2 | `modern_table → apply` |
| `rig_day.fill`: Fill light strength | 0.48 | 0–2, step 0.01 | 0.2 | `modern_table → apply` |
| `rig_night_indoor.gain`: Overall gain | 1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_night_indoor.balance`: White balance (retail to broadcast) | 1 | 0–1, step 0.01 | 0 | `modern_table → apply` |
| `rig_night_indoor.ambient`: Ambient strength | 0.5 | 0–2, step 0.01 | 0.31 | `modern_table → apply` |
| `rig_night_indoor.key`: Key light strength | 0.86 | 0–2, step 0.01 | 0.672 | `modern_table → apply` |
| `rig_night_indoor.fill`: Fill light strength | 0.86 | 0–2, step 0.01 | 0.672 | `modern_table → apply` |
| `rig_alt_day.gain`: Overall gain | 1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_alt_day.balance`: White balance (retail to broadcast) | 1 | 0–1, step 0.01 | 0 | `modern_table → apply` |
| `rig_alt_day.ambient`: Ambient strength | 0.45 | 0–2, step 0.01 | 0.39 | `modern_table → apply` |
| `rig_alt_day.key`: Key light strength | 1.1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_alt_day.fill`: Fill light strength | 0.4 | 0–2, step 0.01 | 0.3675 | `modern_table → apply` |
| `rig_alt_dynamic.gain`: Overall gain | 1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_alt_dynamic.balance`: White balance (retail to broadcast) | 1 | 0–1, step 0.01 | 0 | `modern_table → apply` |
| `rig_alt_dynamic.ambient`: Ambient strength | 0.42 | 0–2, step 0.01 | 0.318 | `modern_table → apply` |
| `rig_alt_dynamic.key`: Key light strength | 1.1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_alt_dynamic.fill`: Fill light strength | 0.4 | 0–2, step 0.01 | 0.3675 | `modern_table → apply` |
| `rig_rain.gain`: Overall gain | 1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_rain.balance`: White balance (retail to broadcast) | 1 | 0–1, step 0.01 | 0 | `modern_table → apply` |
| `rig_rain.ambient`: Ambient strength | 0.46 | 0–2, step 0.01 | 0.348 | `modern_table → apply` |
| `rig_rain.key`: Key light strength | 0.7 | 0–2, step 0.01 | 0.502 | `modern_table → apply` |
| `rig_rain.fill`: Fill light strength | 0.7 | 0–2, step 0.01 | 0.502 | `modern_table → apply` |
| `rig_snow.gain`: Overall gain | 1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_snow.balance`: White balance (retail to broadcast) | 1 | 0–1, step 0.01 | 0 | `modern_table → apply` |
| `rig_snow.ambient`: Ambient strength | 0.5 | 0–2, step 0.01 | 0.4 | `modern_table → apply` |
| `rig_snow.key`: Key light strength | 0.62 | 0–2, step 0.01 | 0.342 | `modern_table → apply` |
| `rig_snow.fill`: Fill light strength | 0.62 | 0–2, step 0.01 | 0.342 | `modern_table → apply` |
| `rig_afternoon.gain`: Overall gain | 1 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_afternoon.balance`: White balance (retail to broadcast) | 1 | 0–1, step 0.01 | 0 | `modern_table → apply` |
| `rig_afternoon.ambient`: Ambient strength | 0.45 | 0–2, step 0.01 | 0.27 | `modern_table → apply` |
| `rig_afternoon.key`: Key light strength | 1.2 | 0–2, step 0.01 | 1 | `modern_table → apply` |
| `rig_afternoon.fill`: Fill light strength | 0.26 | 0–2, step 0.01 | 0.15 | `modern_table → apply` |

Bump flatten 0.68 leaves 0.32 of tangent X/Y amplitude; Z is recomputed. Tint correction 1 uses v2.1: afternoon FFFFEECD → FFFFF5E6; night FFF2FFFF → FFFFFFFF; day vertex (255,255,229) → (255,255,240). Zero keeps retail, two doubles that channel correction with byte clamping.

## Receipts and rebuilding

The existing owner performs all writes. Default hashes in `data/nfl2k5_modern_color_pins.json` remain unchanged. Custom refits use a cache key containing the settings digest, site kind and source hash. Each refit reparses its output and keeps its 32-byte wrapper, decoded size and fixed span. Unfit spans keep their retail bytes and report `unfit` in the receipt.

A completed build writes `<disc>.colour-lighting.json` with the normalized settings, their SHA-256, and the retail/result hashes of every bundle and site. The normal build receipt also contains the bundle pins. Verification checks archive identity, site scope and full bundle hashes. A custom disc without its matching sidecar is not recognized as applied. Keep that sidecar with the disc. Receipts carry hashes and settings, not retail texture or executable bytes.

The owner accepts original retail bytes or the exact already-applied recipe. A different grade requires the original retail source because palette curves are lossy. The Build preflight explains this before copying. The Retail button restores project settings; it cannot undo a baked texture without the original source. Disabling the option on a recognized graded disc likewise requests the original source.

## Offline evidence

- `tests/mod_editor/test_nfl2k5_modern_color.py`: original v2.1 pins and all 477 retail bundle states.
- `tests/mod_editor/test_colour_lighting.py`: model, every control range, seven rig writers, custom XBE replay/restore, wrappers and mips, cache separation, custom receipt tamper/refusal.
- `tests/mod_editor/test_colour_lighting_qt.py`: all controls and swatches, links, class selection, resets, project observers, BuildPlan and actual project archive save/reload.

The existing capability row `nfl2k5.presentation.modern_color_lighting` describes this scope. No rows or executable write spans are added.
