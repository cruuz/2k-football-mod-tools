/* Coaching carousel (job c6-carousel, beta 80): the retail patch sites and the Owner Firing row enter here.
   EXPERIMENTAL. Game routines are reached through absolute addresses in eax; the only relocations are this blob's own
   labels. The parameter block at carousel_params is written by the Studio (mod_editor/core/nfl2k5_coach_carousel.py). */
    .intel_syntax noprefix
    .text
    .globl carousel_advance, carousel_user_gate, carousel_toggle_left, carousel_toggle_right
    .globl carousel_value_text, carousel_widest, carousel_defaults, carousel_params

/* 0x248632, the stage-9 tail of FUN_002480B0: "call 0x247B40" (the season rollover), 5 bytes. ebx is the league menu
   object of the caller. carousel_run (fastcall, ecx = menu) calls the rollover itself, between the record snapshot
   and the decisions, then returns to the instruction after the site. Every register comes back as it was. */
carousel_advance:
    pushad
    mov ecx, ebx
    call carousel_run
    popad
    ret

/* 0x2BA675 in the owner goal check FUN_002BA620: "mov eax,[esi]; test al,4; je 0x2BA6B6" (6 bytes) becomes
   "call carousel_user_gate; nop". Bit 4 of the owner state (esi) is the retail "last warning" mark: with it set, the
   next failed goal ends the user's time with the club. With Owner Firing at All Teams (2) that stays retail; with Off
   (0) or CPU Teams (1) the mark is ignored, so the owner never fires a user. eax leaves holding the state (the mark
   masked out when ignored) and execution resumes where the retail jump would have gone. */
carousel_user_gate:
    mov eax, dword ptr [esi]
    cmp dword ptr [0x00E60144], 2
    je 1f
    and eax, 0xFFFFFFFB
1:  test al, 4
    jne 2f
    mov dword ptr [esp], 0x002BA6B6
2:  ret

/* The Owner Firing row of the franchise options (.rdata 0x500C28): three values instead of Off / On.
   0 = Off, 1 = CPU Teams (the retail "On" value, the retail default), 2 = All Teams. */
carousel_toggle_left:
    mov eax, dword ptr [0x00E60144]
    cmp eax, 2
    jbe 1f
    xor eax, eax
1:  add eax, 2
    cmp eax, 3
    jb 2f
    sub eax, 3
2:  mov dword ptr [0x00E60144], eax
    mov eax, 1
    ret

carousel_toggle_right:
    mov eax, dword ptr [0x00E60144]
    cmp eax, 2
    jbe 1f
    xor eax, eax
1:  inc eax
    cmp eax, 3
    jb 2f
    xor eax, eax
2:  mov dword ptr [0x00E60144], eax
    mov eax, 1
    ret

carousel_value_text:
    mov eax, dword ptr [0x00E60144]
    cmp eax, 2
    jbe 1f
    xor eax, eax
1:  mov eax, dword ptr [carousel_labels + eax * 4]
    ret

/* the widest value text (the row's layout callback): ecx passes through to the retail measure 0x771A0 */
carousel_widest:
    push offset carousel_labels
    push 2
    xor edx, edx
    mov eax, 0x000771A0
    call eax
    ret

/* The MyNFL Options screen's defaults callback (.rdata 0x500A2C, retail 0x148C60, which stores 0 = Off in Owner Firing):
   run the retail reset, then make CPU Teams the default. MyCareer calls 0x148C60 itself, so a career keeps Off. */
carousel_defaults:
    mov eax, 0x00148C60
    call eax
    mov dword ptr [0x00E60144], 1
    ret

    .p2align 2
carousel_labels:
    .long label_off, label_cpu, label_all
label_off:
    .short 'O', 'f', 'f', 0
label_cpu:
    .short 'C', 'P', 'U', ' ', 'T', 'e', 'a', 'm', 's', 0
label_all:
    .short 'A', 'l', 'l', ' ', 'T', 'e', 'a', 'm', 's', 0

/* The model parameters, 184 bytes (layout: PARAMS in nfl2k5_coach_carousel.py). Zero = not filled: the runtime then
   changes nothing. */
    .p2align 4
carousel_params:
    .space 184, 0
