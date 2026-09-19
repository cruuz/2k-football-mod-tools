# b72-s7: live vertices correct; overdraw candidate remains uncalibrated
01. Decoded all 47 scorebug quads and all 188 owned vertices from the requested physical RAM dump.
02. Recorded positions, UVs, diffuse, field ownership and the absence of a stored specular attribute.
03. All five visible down-label glyphs have white 0xffffffff diffuse at all four corners.
04. Their UVs match the intended 1, st, ampersand, 1 and 0 atlas cells.
05. All 3804 compiled table bytes match the pre-s5 layout at ec5d68d4.
06. All 47 live quads match the corresponding baseline native fixture byte-for-byte.
07. The captured black clock and dark quarter colours agree with that baseline's field rows.
08. Current s5 team accents, layout, template, runtime and shipping files remain unchanged.
09. Enumerated all three later draws in the supplied HUD inventory and their geometry intersections.
10. Only draw 395 overlaps the label; vertex 184 is the hang-time event plate, not the brand.
11. Its live UVs sample an opaque RGB 37 event cell and its geometry covers the active label box.
12. The live-data composite gives label mean 37.64 versus screenshot 19.66, error 17.98.
13. Minimum and maximum errors are 18.55 and 17.21, so the within-15 gate fails.
14. Removing that plate restores bright letters only in a counterfactual model, not a validated fix.
15. RAM glyphs encode play clock 17 while the screenshot shows 19; traced state is earlier still.
16. The dumped inactive hang-time material is visible, but bounded native frame replay hides it correctly.
17. No erroneous visibility writer or complete screenshot cause is proved, so no speculative patch is applied.
18. The unchanged RX owner uses 4086 of 4096 bytes, retaining ten spare bytes and 128 RW bytes.
19. All 35 test files, both product closures, provider integrity and native team/order/visibility checks pass; repin changes zero pins.
20. Delivery uses branch b72-s7 in an isolated writable Git store; no emulator, disc or release was produced.
ASTRA_DONE
