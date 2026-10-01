# b76-k1: K128's "needs 128 MB" entry (nfl2k5_k128.REQUIRE_CODE). The XBE entry points here when the disc was built
# with options that need the extra memory. It runs phase 1 like k128_entry (R1's guards, the page count); when the
# machine will not get 128 MB it takes an 8 MB contiguous buffer below 32 MB, scans it out (NV_PCRTC_START, a 32-bit pitch for the
# mode's width, the screen and the display turned on), draws three lines of text into it and stops in a hlt loop
# instead of starting the game (which would otherwise fail later, at the pregame intro).
# Position independent: it sits at +0x200 of the 1 KB K128 code block; R1's guards are at +0xB5, k128_arena at +0x2E,
# the option word at +0x3FC. Assemble: as --32 require_guard.S -o g.o && objcopy -O binary -j .text g.o g.bin
        .intel_syntax noprefix
        .code32
        .text
        .set MM_PAGES, 0x8003B2D4          # MmNumberOfPhysicalPages (4627)
        .set PDE_210, 0xC0300840           # PDE[0x210] through the page-directory self-map
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
go:     test    byte ptr [ebp + (start + 0x1FC - base)], 4    # the early form: phase 2 at once
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
        lea     edx, [ebp + (text - base)]          # records: y (word), x (word), count (byte), glyph indices
3:      movzx   eax, word ptr [edx]
        test    eax, eax
        jz      halt
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
font:   # 0 space, 1 T, 2 H, 3 I, 4 S, 5 B, 6 U, 7 L, 8 D, 9 N, 10 E, 11 M, 12 X, 13 Y, 14 O, 15 R, 16 1, 17 2, 18 8
        .byte 0x00,0x00,0x00,0x00,0x00, 0x01,0x01,0x7F,0x01,0x01, 0x7F,0x08,0x08,0x08,0x7F, 0x00,0x41,0x7F,0x41,0x00
        .byte 0x46,0x49,0x49,0x49,0x31, 0x7F,0x49,0x49,0x49,0x36, 0x3F,0x40,0x40,0x40,0x3F, 0x7F,0x40,0x40,0x40,0x40
        .byte 0x7F,0x41,0x41,0x22,0x1C, 0x7F,0x04,0x08,0x10,0x7F, 0x7F,0x49,0x49,0x49,0x41, 0x7F,0x02,0x1C,0x02,0x7F
        .byte 0x63,0x14,0x08,0x14,0x63, 0x07,0x08,0x70,0x08,0x07, 0x3E,0x41,0x41,0x41,0x3E, 0x7F,0x09,0x19,0x29,0x46
        .byte 0x00,0x42,0x7F,0x40,0x00, 0x42,0x61,0x51,0x49,0x46, 0x36,0x49,0x49,0x49,0x36
text:   # "THIS BUILD NEEDS 128 MB" / "SET XEMU SYSTEM MEMORY" / "TO 128 MB"
        .word 180, 44
        .byte 23, 1,2,3,4,0, 5,6,3,7,8,0, 9,10,10,8,4,0, 16,17,18,0, 11,5
        .word 228, 56
        .byte 22, 4,10,1,0, 12,10,11,6,0, 4,13,4,1,10,11,0, 11,10,11,14,15,13
        .word 276, 212
        .byte 9, 1,14,0, 16,17,18,0, 11,5
        .word 0
