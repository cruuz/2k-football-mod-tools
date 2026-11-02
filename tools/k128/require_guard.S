# b76-k1/b779-km1: K128's "needs 128 MB" entry (nfl2k5_k128.REQUIRE_CODE). The XBE entry points here when the disc was
# built with options that need the extra memory. It runs phase 1 like k128_entry (R1's guards, the page count); when the
# machine will not get 128 MB it takes an 8 MB contiguous buffer below 32 MB, scans it out (NV_PCRTC_START, a 32-bit pitch for the
# mode's width, the screen and the display turned on), draws three lines of text into it and stops in a hlt loop
# instead of starting the game (which would otherwise fail later, at the pregame intro). The message names the failed
# setting (b779-km1): xemu memory below 128 MB keeps the memory lines, and 128 MB with any other guard failing (the
# kernel is not the 4627 build, or an unsupported kernel state) draws the 4627 BIOS lines.
# b780-b11: the memory lines gain two lines (close xemu and open it again: the setting only takes effect at start-up), and the
# BIOS lines gain a line that prints the kernel number the game found and which check failed (CODE 1 kernel is not 4627, 2 the
# memory tables are already in use, 3 the kernel code differs from the 4627 the patch was made for, 4 the page count is odd),
# so a reporter's photo of the screen names the cause. Everything before 'message' (the start-up path) is unchanged.
# Position independent: it sits at +0x200 of the 0x600-byte K128 code block; R1's guards are at +0xB5, k128_arena at +0x2E,
# the option word at +0x3FC. Assemble: as --32 require_guard.S -o g.o && objcopy -O binary -j .text g.o g.bin
        .intel_syntax noprefix
        .code32
        .text
        .set MM_PAGES, 0x8003B2D4          # MmNumberOfPhysicalPages (4627)
        .set PDE_210, 0xC0300840           # PDE[0x210] through the page-directory self-map
        .set CSTATUS, 0xFD10020C           # NV_PFB_CSTATUS: 0x08000000 at 128 MB, 0x04000000 at 64 MB
        .set PCRTC_START, 0xFD600800       # NV2A scanout start (physical)
        .set CRTC_INDEX, 0xFD6013D4        # VGA CRTC index; data at +1
        .set ENTRY, 0x00016BD1             # the title's original entry
        .set SCALE_ROW, 4                  # 4x4 screen pixels per font pixel
start:
        pushad
        pushfd
        call    base
base:   pop     ebp                        # ebp = start + 7
        call    start - 0x200 + 0xB5       # R1's guards: ZF=1 when G1-G4 hold
        jne     fail
        mov     eax, dword ptr [MM_PAGES]
        cmp     eax, 0x4000
        je      set
        cmp     eax, 0x8000
        jne     fail
set:    mov     dword ptr [MM_PAGES], 0x8000
go:     test    byte ptr [ebp + (start + 0x3FC - base)], 4    # the early form: phase 2 at once (options at 0x5FC)
        jz      late
        popfd
        popad
        call    start - 0x200 + 0x2E       # k128_arena (its own guards; replays a harmless compare)
        push    ENTRY
        ret
late:   popfd
        popad
        push    ENTRY
        ret
halt:   sti                                         # the game never starts; the screen stays as drawn
9:      hlt
        jmp     9b
fail:   cmp     dword ptr [MM_PAGES], 0x8000        # 128 MB already managed (tables and count from an earlier start)
        jne     message
        cmp     dword ptr [PDE_210], 0x04000067
        je      go
message:
        push    4                                   # PAGE_READWRITE
        push    0                                   # no alignment beyond a page
        push    0x01FFFFFF                          # below 32 MB: away from the boot animation's buffers (xemu keeps
        push    0                                   # them as GPU surfaces and shows those, not RAM, at their address)
        push    0x00800000                          # 8 MB: up to 1920 x 1080 32-bit pixels
        call    dword ptr [0x004E3CA4]              # MmAllocateContiguousMemoryEx (the title's own import)
        test    eax, eax
        jz      halt                                # no buffer: stop without drawing
        mov     esi, eax                            # the buffer, 0x80000000 | physical
        and     eax, 0x03FFFFFF
        mov     dword ptr [PCRTC_START], eax        # scan it out (a fresh address: xemu shows it from RAM)
        mov     edx, CRTC_INDEX
        mov     byte ptr [edx], 0x01                # the mode's width is (CR01 + 1) * 8 pixels
        movzx   ebx, byte ptr [edx + 1]
        inc     ebx
        shl     ebx, 5                              # pitch = width * 4 bytes
        mov     eax, ebx
        shr     eax, 3                              # offset = pitch / 8: CR13 low byte, CR19 bits 7:5 = bits 10:8
        mov     byte ptr [edx], 0x13
        mov     byte ptr [edx + 1], al
        shr     eax, 3
        and     al, 0xE0
        mov     byte ptr [edx], 0x19
        mov     byte ptr [edx + 1], al
        mov     byte ptr [edx], 0x28
        or      byte ptr [edx + 1], 3               # 32-bit pixels
        mov     al, byte ptr [edx + 6]              # 0x3DA: reset the attribute flip-flop
        mov     byte ptr [edx - 0x14], 0x20         # 0x3C0: attribute index, display enabled
        mov     edx, 0xFD0C03C4                     # the VGA sequencer
        mov     byte ptr [edx], 1
        and     byte ptr [edx + 1], 0xDF            # SR01: screen on
        mov     edi, esi                            # clear the buffer to black
        mov     ecx, 0x00200000
        xor     eax, eax
        rep     stosd
        cmp     dword ptr [CSTATUS], 0x08000000      # the memory itself is right: another guard failed (BIOS/kernel)
        lea     edx, [ebp + (kernel_text - base)]
        je      kern
        lea     edx, [ebp + (text - base)]
        push    1                                   # nothing to add after the memory lines
        jmp     draw
kern:   push    0                                   # the kernel line follows the BIOS lines
draw:
3:      movzx   eax, word ptr [edx]
        test    eax, eax
        jz      tail
        movzx   ecx, word ptr [edx + 2]
        imul    eax, ebx
        add     eax, esi
        lea     edi, [eax + ecx*4]                  # the line's first pixel
        movzx   ecx, byte ptr [edx + 4]
        add     edx, 5
4:      movzx   eax, byte ptr [edx]                 # one character
        inc     edx
        push    ecx
        push    esi
        push    edi
        lea     esi, [ebp + (font - base)]
        lea     eax, [eax + eax*4]
        add     esi, eax                            # its 5 column bytes, bit 0 = top row
        push    5
        pop     ecx
5:      lodsb
        push    edi
        push    ecx
        push    7
        pop     ecx
6:      shr     al, 1
        jnc     7f
        push    edi
        push    ecx
        push    eax
        or      eax, -1                             # white
        push    SCALE_ROW
        pop     ecx
8:      mov     dword ptr [edi], eax
        mov     dword ptr [edi + 4], eax
        mov     dword ptr [edi + 8], eax
        mov     dword ptr [edi + 12], eax
        add     edi, ebx
        loop    8b
        pop     eax
        pop     ecx
        pop     edi
7:      lea     edi, [edi + ebx*4]                  # four rows down
        loop    6b
        pop     ecx
        pop     edi
        add     edi, 16                             # four pixels right
        loop    5b
        pop     edi
        pop     esi
        pop     ecx
        add     edi, 96                             # the next 6-column cell
        loop    4b
        jmp     3b
tail:   cmp     dword ptr [esp], 0                  # 0 only after the BIOS lines: add the kernel line once
        jne     halt
        mov     dword ptr [esp], 1                  # (the finished line's first dword is not 0, so the next pass halts)
        sub     esp, 28                             # the line's record on the stack: 7 dwords
        push    esi
        mov     edi, esp
        add     edi, 4
        lea     esi, [ebp + (kernel_line - base)]
        mov     ecx, 7
        cld
        rep     movsd
        pop     esi
        mov     eax, dword ptr [0x004E3BA4]         # the title's thunk of XboxKrnlVersion (the guards read it too)
        movzx   eax, word ptr [eax + 4]             # .Build
        lea     edi, [esp + 15]                     # the last of the five digit cells (record offset 15)
        mov     ecx, 5
7:      xor     edx, edx
        div     dword ptr [ebp + (ten - base)]
        movzx   edx, byte ptr [ebp + edx + (digits - base)]
        mov     byte ptr [edi], dl
        dec     edi
        loop    7b
        lea     edi, [esp + 11]                     # leading zeros become spaces (all but the last digit)
        mov     ecx, 4
8:      cmp     byte ptr [edi], 30                  # the glyph of '0'
        jne     9f
        mov     byte ptr [edi], 0
        inc     edi
        loop    8b
9:      mov     eax, dword ptr [0x004E3BA4]         # which check failed first (the guards' order)
        cmp     word ptr [eax + 4], 0x1213
        mov     cl, 1                               # CODE 1: the kernel is not the 4627 build
        jne     5f
        cmp     dword ptr [PDE_210], 0
        mov     cl, 2                               # CODE 2: the memory tables are already in use
        jne     5f
        cmp     dword ptr [0x8001F91A], 0x24748B56
        mov     cl, 3                               # CODE 3: MiAddPhysicalPages is not the 4627 code
        jne     5f
        mov     cl, 4                               # CODE 4: the page count is not 0x4000 or 0x8000
5:      movzx   ecx, cl
        movzx   ecx, byte ptr [ebp + ecx + (digits - base)]
        mov     byte ptr [esp + 22], cl
        mov     edx, esp
        jmp     3b
font:   # 0 space, 1 T, 2 H, 3 I, 4 S, 5 B, 6 U, 7 L, 8 D, 9 N, 10 E, 11 M, 12 X, 13 Y, 14 O, 15 R, 16 1, 17 2, 18 8,
        # 19 4, 20 6, 21 7, 22 (, 23 ), 24 C, 25 P, 26 >, 27 G
        .byte 0x00,0x00,0x00,0x00,0x00, 0x01,0x01,0x7F,0x01,0x01, 0x7F,0x08,0x08,0x08,0x7F, 0x00,0x41,0x7F,0x41,0x00
        .byte 0x46,0x49,0x49,0x49,0x31, 0x7F,0x49,0x49,0x49,0x36, 0x3F,0x40,0x40,0x40,0x3F, 0x7F,0x40,0x40,0x40,0x40
        .byte 0x7F,0x41,0x41,0x22,0x1C, 0x7F,0x04,0x08,0x10,0x7F, 0x7F,0x49,0x49,0x49,0x41, 0x7F,0x02,0x1C,0x02,0x7F
        .byte 0x63,0x14,0x08,0x14,0x63, 0x07,0x08,0x70,0x08,0x07, 0x3E,0x41,0x41,0x41,0x3E, 0x7F,0x09,0x19,0x29,0x46
        .byte 0x00,0x42,0x7F,0x40,0x00, 0x42,0x61,0x51,0x49,0x46, 0x36,0x49,0x49,0x49,0x36, 0x18,0x14,0x12,0x7F,0x10
        .byte 0x3C,0x4A,0x49,0x49,0x30, 0x01,0x71,0x09,0x05,0x03, 0x00,0x1C,0x22,0x41,0x00, 0x00,0x41,0x22,0x1C,0x00
        .byte 0x3E,0x41,0x41,0x41,0x22, 0x7F,0x09,0x09,0x09,0x06, 0x41,0x22,0x14,0x08,0x00, 0x3E,0x41,0x49,0x49,0x38
        # b780-b11: 28 A, 29 K, 30 '0', 31 '3', 32 '5', 33 '9'
        .byte 0x7C,0x12,0x11,0x12,0x7C, 0x7F,0x08,0x14,0x22,0x41, 0x3E,0x51,0x49,0x45,0x3E, 0x21,0x41,0x45,0x4B,0x31
        .byte 0x27,0x45,0x45,0x45,0x39, 0x06,0x49,0x49,0x29,0x1E
digits: .byte 30,16,17,31,19,32,20,21,18,33        # the glyph of each decimal digit 0..9
        .balign 4
ten:    .long 10
kernel_line:   # "KERNEL", five digit cells (a 4-digit build leaves the first a space), " CODE ", the check number
        .word 324, 104                                # y 324, x 104 (18 cells centred in 640)
        .byte 18, 29,10,15,9,10,7, 0,0,0,0,0, 0,24,14,8,10,0, 0
        .word 0
        .byte 0,0,0                                   # pads the record to 7 dwords
text:   # "THIS BUILD NEEDS 128 MB" / "SET XEMU SYSTEM MEMORY" / "TO 128 MB"
        .word 180, 44
        .byte 23, 1,2,3,4,0, 5,6,3,7,8,0, 9,10,10,8,4,0, 16,17,18,0, 11,5
        .word 228, 56
        .byte 22, 4,10,1,0, 12,10,11,6,0, 4,13,4,1,10,11,0, 11,10,11,14,15,13
        .word 276, 212
        .byte 9, 1,14,0, 16,17,18,0, 11,5
        .word 324, 92                                # "THEN CLOSE XEMU AND" / "OPEN IT AGAIN": xemu reads the setting at start-up
        .byte 19, 1,2,10,9,0, 24,7,14,4,10,0, 12,10,11,6,0, 28,9,8
        .word 372, 164
        .byte 13, 14,25,10,9,0, 3,1,0, 28,27,28,3,9
        .word 0
kernel_text:  # "THIS BUILD NEEDS THE 4627" / "XBOX BIOS (COMPLEX 4627)" / "IN XEMU SETTINGS > SYSTEM"
        .word 180, 20
        .byte 25, 1,2,3,4,0, 5,6,3,7,8,0, 9,10,10,8,4,0, 1,2,10,0, 19,20,17,21
        .word 228, 32
        .byte 24, 12,5,14,12,0, 5,3,14,4,0, 22,24,14,11,25,7,10,12,0, 19,20,17,21,23
        .word 276, 20
        .byte 25, 3,9,0, 12,10,11,6,0, 4,10,1,1,3,9,27,4,0, 26,0, 4,13,4,1,10,11
        .word 0
