/* Franchise history capture (b780 J3): the three retail sites enter here. EXPERIMENTAL.
   Game routines and the displaced targets are reached with push/ret (every register as the site left it). */
    .intel_syntax noprefix
    .text
    .globl history_played, history_simulated, history_close, hst_config

/* 0x1356C8, the tail of FUN_001356C0 (a played game: the commit ran, ecx = 0): "jmp 0x73770", 5 bytes. */
history_played:
    pushfd
    pushad
    mov ecx, 2
    call history_game
    popad
    popfd
    push 0x00073770
    ret

/* 0x1356FF, the tail of FUN_001356D0 (a simulated game: the commit ran, ecx = 1): "jmp 0x73770", 5 bytes. */
history_simulated:
    pushfd
    pushad
    mov ecx, 4
    call history_game
    popad
    popfd
    push 0x00073770
    ret

/* 0x248601 in FUN_002480B0 stage 9 (after the Super Bowl notice and the retirement pass): "call 0x13ED70", 5 bytes,
   ecx = 0. The displaced target runs as a tail call and returns to 0x248606. */
history_close:
    pushfd
    pushad
    call history_season_close
    popad
    popfd
    push DWORD PTR [hst_config + 12]
    ret

    .balign 16
hst_config:
    .long 0x43545348                    /* +0  "HSTC" */
    .long 1                             /* +4  version */
    .long 0                             /* +8  the footer host's xt_body */
    .long 0                             /* +12 the displaced season-close call target */
    .long 0, 5, 15, 5                   /* +16 hall bar, wait, window, class size */
    .long 0                             /* +32 flags */
    .long 0, 0, 0, 0, 0, 0, 0           /* +36 reserved */
