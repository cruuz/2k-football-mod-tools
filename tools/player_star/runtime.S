/* Original i386 code. Rebuilt by build_runtime.py; all mutable state is on
 * the stack. The five sections are independently reference-audited spans.
 * Units and position interpolation match FUN_000f9030 before quantization. */
.intel_syntax noprefix
.code32

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
    mov esi, dword ptr [0x00e60268]
    mov edi, 22                    /* physical entity array: 22 * 0x50 */
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
    call star_draw
frame_next:
    mov esi, dword ptr [esi+0x30]
    dec edi
    jnz frame_loop
frame_done:
    pop edi
    pop esi
frame_return:
    ret

.section .star_setup,"ax"
.global star_draw
star_draw:                          /* esi = entity, preserves all nonvolatile regs */
    push ebp
    mov ebp, esp
    push ebx
    push esi
    push edi
    and esp, -16
    sub esp, 0xa0                  /* point 0, center 0x10, material 0x20 */
    mov ebx, dword ptr [esi+4]
    mov esi, dword ptr [0x00ba28ac] /* controller material: known registered draw group */
    lea edi, [esp+0x20]
    mov ecx, 32
    rep movsd
    mov dword ptr [esp+0x38], -1   /* material diffuse = opaque white */
    mov dword ptr [esp+0x50], 0    /* untextured; no controller ring atlas */
    and dword ptr [esp+0x80], 0xf0ffffff /* disable culling on our flat strip */
    mov dword ptr [esp+4], 0x40400000 /* y = 3 above the field, below feet */
    mov dword ptr [esp+12], 0x3f800000 /* homogeneous w = 1 */
    jmp star_position

.section .star_position,"ax"
.global star_position
star_position:
    fld dword ptr [ebx+0x130]
    fadd dword ptr [ebx+0x230]
    fmul dword ptr [0x004e4184]     /* 0.5 */
    fstp dword ptr [esp+0x10]
    fld dword ptr [ebx+0x138]
    fadd dword ptr [ebx+0x238]
    fmul dword ptr [0x004e4184]
    fstp dword ptr [esp+0x14]
    lea eax, [esp+0x20]
    push 0                        /* identity world transform */
    push eax
    push 6                        /* NV097 triangle strip */
    xor ecx, ecx                  /* diffuse vertex color */
    mov edx, 1                    /* retail world-space calling convention */
    call 0x0002d2a0
    mov ebx, offset star_points
    mov edi, 22                   /* outer/inner pair at 11 points (closed) */
    jmp star_vertex

.section .star_vertex,"ax"
.global star_vertex
star_vertex:
    fld dword ptr [ebx]
    fld dword ptr [ebx+4]
    test edi, 1
    jz vertex_outer
    fmul dword ptr [star_inset]
    fxch st(1)
    fmul dword ptr [star_inset]
    fxch st(1)
vertex_outer:
    fadd dword ptr [esp+0x14]
    fstp dword ptr [esp+8]
    fadd dword ptr [esp+0x10]
    fstp dword ptr [esp]
    mov ecx, esp
    call 0x0002ca70                /* real inline vertex submission, no GPU stub in game */
    test edi, 1
    jz vertex_same_point
    add ebx, 8
    cmp edi, 3
    jne vertex_same_point
    mov ebx, offset star_points    /* repeat first point for final pair */
vertex_same_point:
    dec edi
    jnz star_vertex
    call 0x0002ca00
    lea esp, [ebp-12]
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret

.section .star_points,"a"
.global star_points, star_inset
star_inset:
    .float 0.84
star_points:
    /* Ten perimeter points, alternating outer radius 72 and notch radius 34.
     * x/z pairs; draw tests verify the emitted perimeter and hollow rim area. */
    .float 0.0, -72.0
    .float 19.98469857794409, -27.50657780874821
    .float 68.47606917325105, -22.24922359499622
    .float 32.33592155403523, 10.50657780874821
    .float 42.32053816505807, 58.24922359499622
    .float 0.0, 34.0
    .float -42.32053816505807, 58.24922359499622
    .float -32.33592155403523, 10.50657780874821
    .float -68.47606917325105, -22.24922359499622
    .float -19.98469857794409, -27.50657780874821
