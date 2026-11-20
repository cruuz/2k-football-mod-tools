/* Called after both players are healthy and the GAD is absent from the
   native line. The surrounding builder restores all general registers. */
.intel_syntax noprefix
.text
.global assign_if_fast
assign_if_fast:
    mov ecx,[ebp-4]                   /* the designated receiving slot */
    mov esi,[edx+ecx*4]               /* the native pick for that slot */
    mov bl,[eax+0x36]                 /* unsigned native Speed attribute */
    cmp bl,[esi+0x36]
    jb slower
    mov [edx+ecx*4],eax
slower:
    ret
.section .note.GNU-stack,"",@progbits
