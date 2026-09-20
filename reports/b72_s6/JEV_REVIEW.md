# Jev review

The installed `jev_diff_gate.py` recipe ran its deterministic checks on `ebed4b99..edef5c97`: zero findings. Its exact 13 request windows and six typed questions per window were routed through the live Jev MCP service because shell networking is restricted. Requests, responses and the unchanged recipe's replay report are retained. There were zero model-call errors.

Jev flagged two `xemu_model.py` windows as WEAKENS_SAFETY (0.69 and 0.67). Manual disposition:

- Texture decoding moved from container slices into a shared raw decoder. The TXTR format/dimension/mip validation remains in `texture`; `p8_texture` additionally requires exact index/palette lengths and bounded power-of-two dimensions. The rectangular swizzle regression and the native independent-decoder equivalence test cover the change. No validation is removed.
- The fixture's single accepted filter became two explicit accepted filters, adding the value observed in the live trace. This is an intentional diagnostic-model extension. The format still requires exactly one mip, address modes remain checked, unsupported filter words are refused, and incomplete live programs are refused. Native tests cover both acceptance and rejection. It does not alter guest GPU state or lift the calibration gate.

Two high pinned-value scores were automatically cleared by the recipe after hashing the replacement pins against the committed source. Provider integrity and both release/runtime closures are also checked independently. Jev's text judgments do not establish visual correctness or an in-game witness.

The installed handoff `factcheck.py` recipe also ran through MCP over 62 claim sentences. It raised 14 review flags and marked one item not covered by the prose evidence. Each was reviewed against the direct receipts:

| Flagged subject | Disposition and direct evidence |
|---|---|
| Base commit and branch, two sentences | `git log` in the owned store establishes ebed4b99 -> edef5c97 on b72-s6. Delivery is verified after the final commit. |
| Six earlier atlas draws and two logo draws | `earlier_hud_draws.json` contains exactly eight rows; six have atlas offset 0x01e55480 and two use logo textures. Material correspondence remains inferred. |
| Identical label/score state and constants | `write_method_table.py` compares draws 392 and 393 and prints an empty state-difference map. Programs, c6 and vertex colours are separately retained in JSON. |
| Unknown state and write provenance | `live.py` supplies no defaults; every recorded state/constant entry has a corresponding write-line map. |
| Requested decisive evidence | `NEXT_CAPTURE.md` is a capture specification, not a report of an executed capture. |
| Test coverage list | The individual order, visibility, GPU, provider and portability test logs all pass; the 35-file result inventory is machine-generated. |
| Stale cave source set | `manifest_freshness.log` first identifies scorebug_exact.py. `manifest_sources.json` compares all seven stale entries with the base and finds no new stale entries. |
| Skill usage | The session read /home/noah/.codex/skills/jev-2k-testing/SKILL.md and made real MCP calls; recipe requests and responses are retained. |
| Bundle location | This is a delivery step checked with `git bundle verify` after the final commit, outside the earlier prose evidence set. |
| Sample method/draw counts | `sample_summary.json` directly records 60972 handled events, 788 closed draws and an empty boundary-event list. |
| Actual build/RAM byte identity | `ram_build_comparison.json` records equal hashes and zero changed bytes in both complete regions from the disc-p patch. |
| Capture cleanup wording | Clarified the summary to say the specification *requires* bounded tracing and cleanup. No capture controller was executed or presented as tested. |
| Jev identified as a person | False positive: Jev is the typed decision service, not a community member or reporter. |

The one uncovered item concerns the owned Git store. Its location follows the filesystem restrictions and is directly verifiable from its config and refs. The original recipe output and raw responses are preserved; review flags were not suppressed or rescored. None authorizes an in-game success claim.
