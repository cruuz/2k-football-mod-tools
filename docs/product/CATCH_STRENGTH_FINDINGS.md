# Catch-strength findings for 2K5 Mod Studio

Status: bounded executable transport proved offline; gameplay A/B still pending  
Date: 2026-07-18

## Product conclusion

An emulator-only route now exists for sending Human and CPU Catching values
beyond the in-game slider's normal maximum. The route is narrow, reversible,
and does not modify the source XISO. It is not yet exposed as a product preset,
because runtime sampling has not proved final catch/drop polarity, downstream
clamping, or effect size.

The current candidate redirects the two gameplay Catching getters to an
existing `2.0f` constant in the executable. This is the requested
"effective 200" input at the cached gameplay-slider boundary; it is not yet a
claim that catches become exactly twice as successful on the field.

## Recovered executable path

The live Human and CPU Catching globals are virtual `.data`/BSS addresses and
therefore do not have file bytes that can simply be replaced. The gameplay
snapshot routine at virtual address `0x0017B8A0` obtains all nine Human and
nine CPU slider values through getter tables and caches them for gameplay.

The Catching entries are tiny file-backed getters:

- Human Catching getter: `0x0017B6D0`, normally loads global `0x00E600F4`;
- CPU Catching getter: `0x0017B880`, normally loads global `0x00E60118`.

Each getter is an x87 absolute float load followed by a return. Redirecting
only its four-byte address operand changes the value entering the normal cache
without introducing code, expanding a section, or touching unrelated sliders.

Three existing read-only float constants provide bounded candidates:

| Preset | Float | Existing constant VA |
| --- | ---: | ---: |
| Experimental 125 | `1.25f` | `0x004EF1CC` |
| Experimental 150 | `1.50f` | `0x004EDB34` |
| Experimental 200 | `2.00f` | `0x004EDB00` |

The writer recomputes the XBE `.text` section SHA-1 after changing the two
operands. The retail RSA signature bytes remain untouched, but the retail
signature is necessarily no longer valid. This makes the route xemu-only;
original Xbox hardware is unsupported.

## Completed 200 candidate experiment

The experiment tool built a new 6,300,499,968-byte XISO from the pinned USA
retail source. It opened the source read-only, copied it to an exclusively
created output, patched the copied `default.xbe`, independently compared the
full source and output, and confirmed that the source hash was unchanged.

- Source SHA-256 before and after:
  `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`
- Effective input candidate: `2.0f`
- Semantic operands replaced: 8 bytes total
- Physically different XISO bytes, including the refreshed section digest: 26
- Output SHA-256:
  `fd73da462fa947b703f1392eae4d6451cd6fa5567660072d36d8825e7eeb463f`
- XDVDFS tree and extents: identical to source
- Runtime claims: deliberately false until the controlled A/B is run

The experiment manifest is private test evidence and is not part of a public
release. The release-safe tool contains addresses, hashes, and patch logic,
not a stock executable span, preimage, section body, or other retail payload.

## Required runtime A/B

Use an isolated xemu profile and the same teams, players, difficulty, sliders,
formations, pass concept, target, and controller timing for stock and patched
runs. Catching remains at the in-game maximum in both conditions; the only
difference is the two getter operands above.

Record at least these outcomes separately:

- catch;
- defender-forced drop after contact;
- clean/open drop;
- interception or breakup;
- uncatchable/inaccurate throw, excluded from the catch-opportunity denominator.

The first useful gate is 50 catchable targets per condition; 100 or more is
preferred. Report catch rate and drop rate with raw counts, not impressions.
Also verify that both Human- and CPU-controlled receivers move in the expected
direction. If the patched build boots but rates do not materially change, the
result falsifies this route as a useful product control or indicates a
downstream clamp.

## Safe product state

- Cached Catching input route: proved offline.
- Experimental 125/150/200 writer: implemented as a private experiment tool.
- 2K5 Mod Studio toggle/preset: locked pending runtime causality.
- Project-file representation if unlocked: preset identifier only; never XBE
  preimages, digest bytes, or retail executable content.
- Revert: omit the executable recipe and rebuild from the untouched source.
- Original Xbox hardware: unsupported.

## Best next step

Boot the stock and Experimental 200 XISOs on the private headless display,
collect the controlled catch sample, and classify the result. A positive result
unlocks three simple emulator-only presets. A negative result ships as a
Coming Soon finding and redirects the next spike to the downstream resolver
that consumes the cached Catching value.
