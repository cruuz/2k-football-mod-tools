/* Beta 81 scoring slice: simulated long field-goal attempts (in place at 0x106EC8; the rest of 88 bytes is int3). Bytes: mod_editor/core/nfl2k5_sim_scoring.py */
.intel_syntax noprefix
.code32
.text
.global start
start:                              /* 0x106EC8: fourth down, quarters 1-3 or leading in Q4 */
    push 0x42260000                 /* 41.5: no field goal from farther than this line-to-goal */
    push 0x42100000                 /* 36.0: always a field goal inside this */
    call 0x101960                   /* lo + u*(hi-lo) from the match RNG */
    fcomp dword ptr [0xa97200]      /* line to goal */
    fnstsw ax
    test ah, 0x41
    jne 0x106ead                    /* draw <= line to goal: punt */
    jmp 0x106f20                    /* field goal */
end:
