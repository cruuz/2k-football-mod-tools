/* Original i386 code. Rebuilt by build_runtime.py; all mutable state is on
 * the stack. The five sections are independently reference-audited spans.
 * Units and position interpolation match FUN_000f9030 before quantization.
 *
 * Beta 76 km2 (Noah: "a white outline of a star but a more modern looking star
 * design"): a hollow white outline star with slim points (inner/outer 0.34), an
 * even 8 cm stroke with mitred tips, over a thin dark under-edge (2.5 cm each
 * side). Each pass is the existing strip of (outer, inner) pairs on the star's
 * ten rays; the points are generated with fsincos (no table), and a pass gives
 * the outer and inner radius at the tips and at the notches, which is exactly
 * the mitred offset contour of the star. A pass whose diffuse alpha is zero is
 * skipped: the outline-only variant drops the under-edge that way. The copied
 * controller material keeps its retail alpha test and blend. */
.intel_syntax noprefix
.code32

/* pass record: +0 outer tip, +4 outer notch, +8 inner tip, +12 inner notch radii (cm),
 * +16 diffuse ARGB, +20 height (cm) */
.set P_OT, 0
.set P_IT, 8
.set P_RGB, 16
.set P_Y, 20
.set P_SIZE, 24

.section .star_frame,"ax"
.global star_frame
star_frame:
    call 0x000f9320                 /* unchanged retail circles */
    cmp dword ptr [0x00ba2818], 0   /* initialized */
    je frame_return
    cmp dword ptr [0x00ba281c], 0   /* HUD visibility */
    je frame_return
    call 0x000627c0                 /* same coach-camera visibility as circles */
    test eax, eax
    jz frame_visible
    call 0x0007d930
    test eax, eax
    jz frame_return
frame_visible:
    push esi
    push edi
    push ebx
    mov esi, dword ptr [0x00e60268]
    push 22                         /* physical entity array: 22 * 0x50 */
    pop edi
frame_loop:
    test esi, esi
    jz frame_done
    cmp dword ptr [esi+0x48], 0     /* same inactive-entity filter as retail */
    jne frame_next
    mov eax, dword ptr [esi+0x3c]
    test eax, eax
    jz frame_next
    test byte ptr [eax+0x53], 1
    jz frame_next
    cmp dword ptr [esi+4], 0
    je frame_next
    mov ebx, offset star_passes
    jmp pass_loop
frame_next:
    mov esi, dword ptr [esi+0x30]
    dec edi
    jnz frame_loop
frame_done:
    pop ebx
    pop edi
    pop esi
frame_return:
    ret

.section .star_setup,"ax"
.global star_draw
star_draw:                          /* esi = entity, ebx = pass record */
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    and esp, -16
    sub esp, 0xa0                   /* vertex 0, centre 0x10, cos/sin 0x18, material 0x20 */
    mov edx, dword ptr [esi+4]
    mov esi, dword ptr [0x00ba28ac] /* controller material: known registered draw group */
    lea edi, [esp+0x20]
    push 32
    pop ecx
    rep movsd
    mov eax, dword ptr [ebx+P_RGB]
    mov dword ptr [esp+0x38], eax   /* private material diffuse */
    and dword ptr [esp+0x50], 0     /* untextured; no controller ring atlas */
    and byte ptr [esp+0x83], 0xf0   /* disable culling on our flat strip */
    mov eax, dword ptr [ebx+P_Y]
    mov dword ptr [esp+4], eax      /* this pass's height above the turf */
    jmp star_position

.section .star_position,"ax"
.global star_position
star_position:
    fld dword ptr [edx+0x130]
    fadd dword ptr [edx+0x230]
    fmul dword ptr [0x004e4184]     /* 0.5 */
    fstp dword ptr [esp+0x10]
    fld dword ptr [edx+0x138]
    fadd dword ptr [edx+0x238]
    fmul dword ptr [0x004e4184]
    fstp dword ptr [esp+0x14]
    lea eax, [esp+0x20]
    push 0                          /* identity world transform */
    push eax
    push 6                          /* NV097 triangle strip */
    xor ecx, ecx                    /* diffuse vertex color */
    mov edx, 1                      /* retail world-space calling convention */
    call 0x0002d2a0
    xor edi, edi                    /* ray k = 0..10; ray 10 repeats ray 0 and closes the strip */
    jmp star_ray

.section .star_vertex,"ax"
.global star_vertex, star_ray
star_ray:
    mov dword ptr [esp+0x18], edi
    fild dword ptr [esp+0x18]
    fmul dword ptr [star_step]      /* angle = k * pi / 5 */
    fsincos
    fstp dword ptr [esp+0x18]       /* cos */
    fstp dword ptr [esp+0x1c]       /* sin */
    mov eax, edi
    and eax, 1                      /* 0 on a tip ray, 1 on a notch ray */
    lea eax, [ebx+eax*4]
star_vertex:                        /* eax = the pass's radius pair for this ray */
    call star_emit                  /* the outer contour */
    add eax, P_IT
    call star_emit                  /* the inner contour */
    inc edi
    cmp edi, 10
    jbe star_ray
    call 0x0002ca00
    lea esp, [ebp-12]
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret
star_emit:                          /* eax -> radius; the draw frame starts at esp+8 after the push */
    push eax
    fld dword ptr [eax]
    fld st(0)
    fmul dword ptr [esp+8+0x1c]     /* r sin */
    fadd dword ptr [esp+8+0x10]     /* + centre x */
    fstp dword ptr [esp+8]          /* x */
    fmul dword ptr [esp+8+0x18]     /* r cos */
    fsubr dword ptr [esp+8+0x14]    /* centre z - r cos */
    fstp dword ptr [esp+8+8]        /* z */
    lea ecx, [esp+8]
    call 0x0002ca70                 /* real inline vertex submission, no GPU stub in game */
    pop eax
    ret

.section .star_points,"ax"
.global star_passes, star_passes_end, star_step, pass_loop
pass_loop:                          /* esi = entity, ebx = the first pass */
    cmp byte ptr [ebx+P_RGB+3], 0   /* a dropped pass (alpha 0) */
    je pass_next
    call star_draw                  /* esi = entity, ebx = pass; both preserved */
pass_next:
    add ebx, P_SIZE
    cmp ebx, offset star_passes_end
    jb pass_loop
    jmp frame_next
star_step:
    .float 0.6283185307179586       /* pi / 5 */
star_passes:
    /* the dark under-edge: 2.5 cm outside and inside the white stroke (alpha 0 drops it: the outline variant) */
    .float 95.80690143038373, 32.57434648633048, 46.89101399238835, 15.942944757412036
    .long 0xc80e0e10
    .float 5.0
    /* the white outline: the star (tips 86.4, notches 29.376) and its 8 cm inward mitred offset */
    .float 86.4, 29.376, 56.297915422772085, 19.141291243742508
    .long 0xffffffff
    .float 5.5
star_passes_end:
