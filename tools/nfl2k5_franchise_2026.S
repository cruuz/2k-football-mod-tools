/* The only absolute reference is an allocator-owned RW page. No retail hook.
 * The caller initializes this workspace with franchise_kernel op 0 before use. */
.intel_syntax noprefix
.section .text
.global franchise_workspace
franchise_workspace:
 mov eax, offset workspace
 ret
.section .note.GNU-stack,"",@progbits
