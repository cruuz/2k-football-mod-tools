# Earlier live HUD method comparison

This is the 13:55:28 window in the original session trace, not the supplied 13:55:49 sample. Label/score names are inferred from the later RAM descriptor sequence; the logger omitted the actual index values. Line numbers refer to the full trace.log. JSON retains every observed register, complete resident program memory, every observed constant component and its last write line. Missing means unknown.

Inferred label: draw 392, BEGIN line 157489. Inferred scores: draw 393, BEGIN line 157500. First sprite vertex-array setup: line 156855.

| Method | Label | Scores | Last write line, label / scores | Provenance |
|---|---|---|---|---|
| 0x0184 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0188 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0190 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0194 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0198 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x019c | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x01a0 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0200 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0204 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0208 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x020c | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0210 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0214 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0260 | 0xd8d41010 | 0xd8d41010 | 157031 / 157031 | sprite setup or earlier sprite material |
| 0x0264 | 0x00000000 | 0x00000000 | 157032 / 157032 | sprite setup or earlier sprite material |
| 0x0268 | 0x00000000 | 0x00000000 | 157033 / 157033 | sprite setup or earlier sprite material |
| 0x026c | 0x00000000 | 0x00000000 | 157034 / 157034 | sprite setup or earlier sprite material |
| 0x0270 | 0x00000000 | 0x00000000 | 157035 / 157035 | sprite setup or earlier sprite material |
| 0x0274 | 0x00000000 | 0x00000000 | 157036 / 157036 | sprite setup or earlier sprite material |
| 0x0278 | 0x00000000 | 0x00000000 | 157037 / 157037 | sprite setup or earlier sprite material |
| 0x027c | 0x00000000 | 0x00000000 | 157038 / 157038 | sprite setup or earlier sprite material |
| 0x0288 | 0x0f030c00 | 0x0f030c00 | 157039 / 157039 | sprite setup or earlier sprite material |
| 0x028c | 0x11331c80 | 0x11331c80 | 157040 / 157040 | sprite setup or earlier sprite material |
| 0x029c | 0x00002601 | 0x00002601 | 156870 / 156870 | sprite setup or earlier sprite material |
| 0x02a0 | 0x00000002 | 0x00000002 | 156871 / 156871 | sprite setup or earlier sprite material |
| 0x02a4 | 0x00000000 | 0x00000000 | 156819 / 156819 | preceding game state |
| 0x02a8 | 0xff000000 | 0xff000000 | 156872 / 156872 | sprite setup or earlier sprite material |
| 0x02b4 | 0x00000000 | 0x00000000 | 156865 / 156865 | sprite setup or earlier sprite material |
| 0x02c0 | 0x0275005a | 0x0275005a | 156866 / 156866 | sprite setup or earlier sprite material |
| 0x02e0 | 0x01cf0010 | 0x01cf0010 | 156867 / 156867 | sprite setup or earlier sprite material |
| 0x0300 | 0x00000001 | 0x00000001 | 156960 / 156960 | sprite setup or earlier sprite material |
| 0x0304 | 0x00000001 | 0x00000001 | 156961 / 156961 | sprite setup or earlier sprite material |
| 0x0308 | 0x00000001 | 0x00000001 | 156958 / 156958 | sprite setup or earlier sprite material |
| 0x030c | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x0320 | 0x00000000 | 0x00000000 | 156822 / 156822 | preceding game state |
| 0x0324 | 0x00000000 | 0x00000000 | 156823 / 156823 | preceding game state |
| 0x032c | 0x00000000 | 0x00000000 | 156824 / 156824 | preceding game state |
| 0x033c | 0x00000206 | 0x00000206 | 156962 / 156962 | sprite setup or earlier sprite material |
| 0x0340 | 0x00000002 | 0x00000002 | 156963 / 156963 | sprite setup or earlier sprite material |
| 0x0344 | 0x00000302 | 0x00000302 | 156964 / 156964 | sprite setup or earlier sprite material |
| 0x0348 | 0x00000303 | 0x00000303 | 156965 / 156965 | sprite setup or earlier sprite material |
| 0x034c | 0x00000000 | 0x00000000 | 156966 / 156966 | sprite setup or earlier sprite material |
| 0x0350 | 0x00008006 | 0x00008006 | 156967 / 156967 | sprite setup or earlier sprite material |
| 0x0354 | 0x00000203 | 0x00000203 | 156816 / 156816 | preceding game state |
| 0x0358 | 0x01010101 | 0x01010101 | 156820 / 156820 | preceding game state |
| 0x035c | 0x00000001 | 0x00000001 | 156821 / 156821 | preceding game state |
| 0x0360 | 0x000000ff | 0x000000ff | 156825 / 156825 | preceding game state |
| 0x0364 | 0x00000200 | 0x00000200 | 156826 / 156826 | preceding game state |
| 0x0368 | 0x00000000 | 0x00000000 | 156827 / 156827 | preceding game state |
| 0x036c | 0x000000ff | 0x000000ff | 156828 / 156828 | preceding game state |
| 0x0370 | 0x00001e00 | 0x00001e00 | 156829 / 156829 | preceding game state |
| 0x0374 | 0x00001e00 | 0x00001e00 | 156830 / 156830 | preceding game state |
| 0x0378 | 0x00001e00 | 0x00001e00 | 156831 / 156831 | preceding game state |
| 0x037c | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x038c | 0x00001b02 | 0x00001b02 | 156834 / 156834 | preceding game state |
| 0x0394 | 0x00000000 | 0x00000000 | 156868 / 156868 | sprite setup or earlier sprite material |
| 0x0398 | 0x4b833332 | 0x4b833332 | 156869 / 156869 | sprite setup or earlier sprite material |
| 0x039c | 0x00000404 | 0x00000404 | 156959 / 156959 | sprite setup or earlier sprite material |
| 0x03b8 | 0x00000000 | 0x00000000 | 157030 / 157030 | sprite setup or earlier sprite material |
| 0x09c0 | 0x00000000 | 0x00000000 | 156873 / 156873 | sprite setup or earlier sprite material |
| 0x09c4 | 0x00000000 | 0x00000000 | 156874 / 156874 | sprite setup or earlier sprite material |
| 0x09c8 | 0x00000000 | 0x00000000 | 156875 / 156875 | sprite setup or earlier sprite material |
| 0x0a60 | 0x00000000 | 0x00000000 | 157041 / 157041 | sprite setup or earlier sprite material |
| 0x0a64 | 0x00000000 | 0x00000000 | 157042 / 157042 | sprite setup or earlier sprite material |
| 0x0a68 | 0x00000000 | 0x00000000 | 157043 / 157043 | sprite setup or earlier sprite material |
| 0x0a6c | 0x00000000 | 0x00000000 | 157044 / 157044 | sprite setup or earlier sprite material |
| 0x0a70 | 0x00000000 | 0x00000000 | 157045 / 157045 | sprite setup or earlier sprite material |
| 0x0a74 | 0x00000000 | 0x00000000 | 157046 / 157046 | sprite setup or earlier sprite material |
| 0x0a78 | 0x00000000 | 0x00000000 | 157047 / 157047 | sprite setup or earlier sprite material |
| 0x0a7c | 0x00000000 | 0x00000000 | 157048 / 157048 | sprite setup or earlier sprite material |
| 0x0a80 | 0x00000000 | 0x00000000 | 157049 / 157049 | sprite setup or earlier sprite material |
| 0x0a84 | 0x00000000 | 0x00000000 | 157050 / 157050 | sprite setup or earlier sprite material |
| 0x0a88 | 0x00000000 | 0x00000000 | 157051 / 157051 | sprite setup or earlier sprite material |
| 0x0a8c | 0x00000000 | 0x00000000 | 157052 / 157052 | sprite setup or earlier sprite material |
| 0x0a90 | 0x00000000 | 0x00000000 | 157053 / 157053 | sprite setup or earlier sprite material |
| 0x0a94 | 0x00000000 | 0x00000000 | 157054 / 157054 | sprite setup or earlier sprite material |
| 0x0a98 | 0x00000000 | 0x00000000 | 157055 / 157055 | sprite setup or earlier sprite material |
| 0x0a9c | 0x00000000 | 0x00000000 | 157056 / 157056 | sprite setup or earlier sprite material |
| 0x0aa0 | 0x000100c0 | 0x000100c0 | 157057 / 157057 | sprite setup or earlier sprite material |
| 0x0aa4 | 0x00000000 | 0x00000000 | 157058 / 157058 | sprite setup or earlier sprite material |
| 0x0aa8 | 0x00000000 | 0x00000000 | 157059 / 157059 | sprite setup or earlier sprite material |
| 0x0aac | 0x00000000 | 0x00000000 | 157060 / 157060 | sprite setup or earlier sprite material |
| 0x0ab0 | 0x00000000 | 0x00000000 | 157061 / 157061 | sprite setup or earlier sprite material |
| 0x0ab4 | 0x00000000 | 0x00000000 | 157062 / 157062 | sprite setup or earlier sprite material |
| 0x0ab8 | 0x00000000 | 0x00000000 | 157063 / 157063 | sprite setup or earlier sprite material |
| 0x0abc | 0x00000000 | 0x00000000 | 157064 / 157064 | sprite setup or earlier sprite material |
| 0x0ac0 | 0xc8c40000 | 0xc8c40000 | 157065 / 157065 | sprite setup or earlier sprite material |
| 0x0ac4 | 0x00000000 | 0x00000000 | 157066 / 157066 | sprite setup or earlier sprite material |
| 0x0ac8 | 0x00000000 | 0x00000000 | 157067 / 157067 | sprite setup or earlier sprite material |
| 0x0acc | 0x00000000 | 0x00000000 | 157068 / 157068 | sprite setup or earlier sprite material |
| 0x0ad0 | 0x00000000 | 0x00000000 | 157069 / 157069 | sprite setup or earlier sprite material |
| 0x0ad4 | 0x00000000 | 0x00000000 | 157070 / 157070 | sprite setup or earlier sprite material |
| 0x0ad8 | 0x00000000 | 0x00000000 | 157071 / 157071 | sprite setup or earlier sprite material |
| 0x0adc | 0x00000000 | 0x00000000 | 157072 / 157072 | sprite setup or earlier sprite material |
| 0x1720 | 0x01e77f60 | 0x01e77f60 | 156855 / 156855 | sprite setup or earlier sprite material |
| 0x1724 | 0x01e78628 | 0x01e78628 | 156856 / 156856 | sprite setup or earlier sprite material |
| 0x1728 | 0x02b35686 | 0x02b35686 | 155786 / 155786 | preceding game state |
| 0x172c | 0x01e78620 | 0x01e78620 | 156857 / 156857 | sprite setup or earlier sprite material |
| 0x1730 | 0x015f0660 | 0x015f0660 | 155787 / 155787 | preceding game state |
| 0x1734 | 0x015f0664 | 0x015f0664 | 155788 / 155788 | preceding game state |
| 0x1738 | 0x01e78624 | 0x01e78624 | 156858 / 156858 | sprite setup or earlier sprite material |
| 0x1760 | 0x00000631 | 0x00000631 | 156839 / 156839 | preceding game state |
| 0x1764 | 0x00000a15 | 0x00000a15 | 156840 / 156840 | preceding game state |
| 0x1768 | 0x00000002 | 0x00000002 | 156841 / 156841 | preceding game state |
| 0x176c | 0x00000a40 | 0x00000a40 | 156842 / 156842 | preceding game state |
| 0x1770 | 0x00000002 | 0x00000002 | 156843 / 156843 | preceding game state |
| 0x1774 | 0x00000002 | 0x00000002 | 156844 / 156844 | preceding game state |
| 0x1778 | 0x00000a21 | 0x00000a21 | 156845 / 156845 | preceding game state |
| 0x177c | 0x00000002 | 0x00000002 | 156846 / 156846 | preceding game state |
| 0x1780 | 0x00000002 | 0x00000002 | 156847 / 156847 | preceding game state |
| 0x1784 | 0x00000002 | 0x00000002 | 156848 / 156848 | preceding game state |
| 0x1788 | 0x00000002 | 0x00000002 | 156849 / 156849 | preceding game state |
| 0x178c | 0x00000002 | 0x00000002 | 156850 / 156850 | preceding game state |
| 0x1790 | 0x00000002 | 0x00000002 | 156851 / 156851 | preceding game state |
| 0x1794 | 0x00000002 | 0x00000002 | 156852 / 156852 | preceding game state |
| 0x1798 | 0x00000002 | 0x00000002 | 156853 / 156853 | preceding game state |
| 0x179c | 0x00000002 | 0x00000002 | 156854 / 156854 | preceding game state |
| 0x17bc | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x17c0 | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x17f8 | 0x00000000 | 0x00000000 | 157073 / 157073 | sprite setup or earlier sprite material |
| 0x1b00 | 0x01e55480 | 0x01e55480 | 157483 / 157494 | sprite setup or earlier sprite material |
| 0x1b04 | 0x09810b29 | 0x09810b29 | 157484 / 157495 | sprite setup or earlier sprite material |
| 0x1b08 | 0x00010101 | 0x00010101 | 157486 / 157497 | sprite setup or earlier sprite material |
| 0x1b0c | 0x4003ffc0 | 0x4003ffc0 | 157487 / 157498 | sprite setup or earlier sprite material |
| 0x1b14 | 0x02063f00 | 0x02063f00 | 157488 / 157499 | sprite setup or earlier sprite material |
| 0x1b20 | 0x01e75480 | 0x01e75480 | 157485 / 157496 | sprite setup or earlier sprite material |
| 0x1b40 | 0x02462900 | 0x02462900 | 156034 / 156034 | preceding game state |
| 0x1b44 | 0x07750b2d | 0x07750b2d | 156035 / 156035 | preceding game state |
| 0x1b48 | 0x00030303 | 0x00030303 | 156037 / 156037 | preceding game state |
| 0x1b4c | 0x4003ffc0 | 0x4003ffc0 | 156038 / 156038 | preceding game state |
| 0x1b54 | 0x02063f00 | 0x02063f00 | 156039 / 156039 | preceding game state |
| 0x1b60 | 0x024829c0 | 0x024829c0 | 156036 / 156036 | preceding game state |
| 0x1b80 | 0x014ffe00 | 0x014ffe00 | 144615 / 144615 | preceding game state |
| 0x1b84 | 0x0771062d | 0x0771062d | 144616 / 144616 | preceding game state |
| 0x1b88 | 0x00030303 | 0x00030303 | 144617 / 144617 | preceding game state |
| 0x1b8c | 0x4003ffc0 | 0x4003ffc0 | 144618 / 144618 | preceding game state |
| 0x1b94 | 0x02063f00 | 0x02063f00 | 144619 / 144619 | preceding game state |
| 0x1ba0 | 0x017c23c0 | 0x017c23c0 | 141903 / 141903 | preceding game state |
| 0x1bc0 | 0x0155ff00 | 0x0155ff00 | 144811 / 144811 | preceding game state |
| 0x1bc4 | 0x0771062d | 0x0771062d | 144812 / 144812 | preceding game state |
| 0x1bc8 | 0x00030303 | 0x00030303 | 144813 / 144813 | preceding game state |
| 0x1bcc | 0x4003ffc0 | 0x4003ffc0 | 144814 / 144814 | preceding game state |
| 0x1bd4 | 0x02063f00 | 0x02063f00 | 144815 / 144815 | preceding game state |
| 0x1d78 | 0x00000010 | 0x00000010 | 156864 / 156864 | sprite setup or earlier sprite material |
| 0x1d7c | UNKNOWN | UNKNOWN | None / None | unobserved |
| 0x1e20 | 0x00000000 | 0x00000000 | 157074 / 157074 | sprite setup or earlier sprite material |
| 0x1e24 | 0x00000000 | 0x00000000 | 157075 / 157075 | sprite setup or earlier sprite material |
| 0x1e40 | 0x000100c0 | 0x000100c0 | 157076 / 157076 | sprite setup or earlier sprite material |
| 0x1e44 | 0x00000000 | 0x00000000 | 157077 / 157077 | sprite setup or earlier sprite material |
| 0x1e48 | 0x00000000 | 0x00000000 | 157078 / 157078 | sprite setup or earlier sprite material |
| 0x1e4c | 0x00000000 | 0x00000000 | 157079 / 157079 | sprite setup or earlier sprite material |
| 0x1e50 | 0x00000000 | 0x00000000 | 157080 / 157080 | sprite setup or earlier sprite material |
| 0x1e54 | 0x00000000 | 0x00000000 | 157081 / 157081 | sprite setup or earlier sprite material |
| 0x1e58 | 0x00000000 | 0x00000000 | 157082 / 157082 | sprite setup or earlier sprite material |
| 0x1e5c | 0x00000000 | 0x00000000 | 157083 / 157083 | sprite setup or earlier sprite material |
| 0x1e60 | 0x00011101 | 0x00011101 | 157084 / 157084 | sprite setup or earlier sprite material |
| 0x1e70 | 0x00000001 | 0x00000001 | 157085 / 157085 | sprite setup or earlier sprite material |
| 0x1e74 | 0x00000111 | 0x00000111 | 144872 / 144872 | preceding game state |
| 0x1e78 | 0x00000000 | 0x00000000 | 144873 / 144873 | preceding game state |
| 0x1e94 | 0x00000006 | 0x00000006 | 157481 / 157492 | sprite setup or earlier sprite material |
| 0x1e98 | 0x00000000 | 0x00000000 | 157482 / 157493 | sprite setup or earlier sprite material |
| 0x1e9c | 0x00000000 | 0x00000000 | 156968 / 156968 | sprite setup or earlier sprite material |
| 0x1ea0 | 0x00000000 | 0x00000000 | 157480 / 157491 | sprite setup or earlier sprite material |
| 0x1ea4 | 0x00000005 | 0x00000005 | 157453 / 157453 | sprite setup or earlier sprite material |

The provenance names identify when a write occurred relative to the first sprite array setup. They do not prove a CPU call stack. Every value persists until overwritten; CPU shadow caches and host shader uniforms were not dumped. No separate NV097 TFACTOR exists in this stream. All observed stage and final combiner constants are included above.

| Vertex constant | Label | Scores | Last component write lines, label |
|---|---|---|---|
| c0 | [0.84375, 0.0, 0.0, 90.0] | [0.84375, 0.0, 0.0, 90.0] | [156877, 156878, 156879, 156880] |
| c1 | [0.0, 1.0, 0.0, 16.0] | [0.0, 1.0, 0.0, 16.0] | [156881, 156882, 156883, 156884] |
| c2 | [0.0, 0.0, 16793.16796875, -15953.50976562] | [0.0, 0.0, 16793.16796875, -15953.50976562] | [156885, 156886, 156887, 156888] |
| c3 | [0.0, 0.0, 0.0, 1.0] | [0.0, 0.0, 0.0, 1.0] | [156889, 156890, 156891, 156892] |
| c4 | [0.0, 0.0, 1.0, 0.0] | [0.0, 0.0, 1.0, 0.0] | [156954, 156955, 156956, 156957] |
| c5 | [0.25, 0.25, 0.25, 1.0] | [0.25, 0.25, 0.25, 1.0] | [157454, 157455, 157456, 157457] |
| c6 | [0.5, 0.5, 0.5, 0.5] | [0.5, 0.5, 0.5, 0.5] | [156944, 156945, 156946, 156947] |
| c7 | [0.5, 0.5, 0.5, 0.5] | [0.5, 0.5, 0.5, 0.5] | [156949, 156950, 156951, 156952] |
| c8 | [-20.0, 100.0, -29.5, 420.0] | [-20.0, 100.0, -29.5, 420.0] | [156860, 156861, 156862, 156863] |
| c27 | [1.0, 0.0, 0.0, 320.0] | [1.0, 0.0, 0.0, 320.0] | [157087, 157088, 157089, 157090] |
| c28 | [0.0, -1.0, 0.0, 408.0] | [0.0, -1.0, 0.0, 408.0] | [157091, 157092, 157093, 157094] |
| c29 | [0.0, 0.0, 1.0, 100.0] | [0.0, 0.0, 1.0, 100.0] | [157095, 157096, 157097, 157098] |

Both observed 13-instruction programs hash to d2f8707d23d3e86d3d0f0e8d097292495c6701df9f51e3dc037dbae7d2d63867, matching s5. Their colour instruction reads c6, not the differing earlier-material c5 values. The atlas state differs from s5 in LOD bias (-1 versus 0). It has only one mip level, so this does not select darker mip bytes.
