.intel_syntax noprefix
.code32
.section .text
.global revise
# Private duration-roll thresholds on the native 31-bit scale.
.set KEEP4,177044453
.set TWO4,177044453
.set KEEP567,134321371
.set TWO567,134321371
revise:
    pushfd
    cmp ebx,4
    jb finish
    cmp ebx,7
    ja finish
    cmp ebx,4
    jne medium
    cmp edx,KEEP4
    jb finish
    cmp edx,TWO4
    jmp classify
medium:
    cmp edx,KEEP567
    jb finish
    cmp edx,TWO567
classify:
    mov ebx,3
    jae finish
    dec ebx
finish:
    popfd
    jmp 0x1027e8
.section .note.GNU-stack,"",@progbits
