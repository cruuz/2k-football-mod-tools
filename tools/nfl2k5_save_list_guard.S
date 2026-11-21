/* Boot save browser. Build: as --32 -o guard.o nfl2k5_save_list_guard.S
 * ld -m elf_i386 -Ttext=0x294960 --oformat=binary -o guard.bin guard.o
 * Each aligned RET belongs to the original game. Only the 15 otherwise
 * unreachable alignment bytes following each RET are installed. */
.intel_syntax noprefix
.text
.macro slot offset
.org \offset, 0x90
ret
.endm

slot 0
checked_length:
    push ecx
    push edx
    xor edx, edx
    test cl, 1
    jnz empty
    test ecx, ecx
    jz empty                 /* live save metadata also uses the Xbox high-address kernel pool */
    jmp check_page

slot 16
check_page:
    push ecx
    push edx
    push ecx
    call DWORD PTR [0x4e3ba0]  /* existing MmQueryAddressProtect import */
    pop edx
    pop ecx
    jmp check_flags

slot 32
check_flags:
    test ah, 1                /* PAGE_GUARD */
    jnz empty
    test al, 0xee             /* PAGE_READ* or PAGE_EXECUTE_READ* */
    jz empty
    jmp check_character

slot 48
check_character:
    cmp WORD PTR [ecx], 0
    je finished
    cmp dl, 128               /* Xbox MAX_GAMENAME, in UTF-16 code units */
    jae empty
    jmp advance

slot 64
advance:
    inc edx
    add ecx, 2
    test cx, 0x0fff
    jz check_page
    jmp check_character

slot 80
empty:
    xor edx, edx
finished:
    mov eax, edx
    pop edx
    pop ecx
    ret

slot 96
checked_type:
    mov ecx, edi
    call checked_length
    test eax, eax
    jnz retail_match
    ret

slot 112
retail_match:
    push esi
    xor esi, esi
    jmp 0x16a610             /* original matcher after its prologue */
.org 128, 0x90
