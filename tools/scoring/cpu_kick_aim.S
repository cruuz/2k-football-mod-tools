/* Beta 81 scoring slice: CPU place-kick aim (in place at 0x2EF5F5, 27 bytes). Bytes: mod_editor/core/nfl2k5_cpu_kick_aim.py */
.intel_syntax noprefix
.code32
.text
.global start
start:                              /* 0x2EF5F5: EDX = signed CPU aim error just drawn */
    imul edx, edx, 85               /* scale by 85/128 (about 2/3) */
    mov eax, dword ptr [ebp+8]
    mov eax, dword ptr [eax+0x38]
    test eax, eax
    je 1f
    cmp dword ptr [eax+0x30], 0
    je 1f
    lea edx, [edx+edx*2]            /* the original x1.5 case keeps its ratio */
    sar edx, 1
1:  sar edx, 7
end:
