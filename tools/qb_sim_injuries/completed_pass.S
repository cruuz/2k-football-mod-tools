.intel_syntax noprefix
.code32
.section .text
.global completed_catch_scale
completed_catch_scale:
    fld dword ptr [SPOT]
    fcomp dword ptr [RZ_LINE]
    fnstsw ax
    test ah, 0x41
    je convert
    fld dword ptr [esp+4]
    call REDZONE_GAIN
    nop
    fstp dword ptr [esp+4]
convert:
    mov eax, [esp]
    mov dword ptr [RETURN_SLOT], eax
    pop eax
    call YARD_CONVERT
    call COMPLETED_GAIN
    nop
    mov edx, dword ptr [RETURN_SLOT]
    push edx
    ret
.section .note.GNU-stack,"",@progbits
