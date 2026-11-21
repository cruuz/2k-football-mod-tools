.intel_syntax noprefix
.code32
.section .text
.global clinical_return
clinical_return:
    # The original selector returns either zero or one. JECXZ leaves flags intact.
    xchg eax,ecx
    jecxz captured
    # The selector's final ADD ESP,0x24 had a different operand while using copied arguments.
    # This is its original stack address just before 0x102872 at the unwrapped call.
    lea ecx,[esp-48]
    add ecx,0x24
    mov ecx,1
captured:
    xchg eax,ecx
    pushfd
    pushad
    mov ecx,esp
    sub esp,528
    jmp CONTINUE_CAPTURE
.section .note.GNU-stack,"",@progbits
