#ifndef VC_STATIC_RUNTIME_APF_BOOT_LEAF_ADAPTERS_H
#define VC_STATIC_RUNTIME_APF_BOOT_LEAF_ADAPTERS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Isolated APF 2K8 guest-ABI leaf adapters.
 *
 * This module is not linked into the normal SDL/OpenGL host shell. A future
 * static-runtime driver may call it only after binding an explicit guest
 * thread and checking every non-OK dispatch result.
 */

#define VC_APF_BOOT_TLS_SLOT_COUNT 2048u
#define VC_APF_BOOT_MAX_GUEST_THREADS 64u
#define VC_APF_BOOT_TLS_OUT_OF_INDEXES UINT32_MAX

/*
 * Xenia's Xenon object-table namespace starts at 0xF8000000 and reserves
 * slot zero. This bounded adapter owns only the following event slots; they
 * are handles, never guest pointers.
 */
#define VC_APF_BOOT_MAX_EVENT_HANDLES 64u
#define VC_APF_BOOT_EVENT_HANDLE_BASE 0xF8000000u
#define VC_APF_BOOT_FIRST_EVENT_HANDLE 0xF8000004u
#define VC_APF_BOOT_EVENT_NAME_MAX 255u

/* Exact fixed buffers built by APF before its sole message-box import. */
#define VC_APF_BOOT_UI_MESSAGE_MAX_CODE_UNITS 255u
#define VC_APF_BOOT_UI_BUTTON_MAX_CODE_UNITS 31u
#define VC_APF_XAM_OVERLAPPED_SIZE 28u

/* Exact thread shape reached by the 458-node augmented pre-main frontier. */
#define VC_APF_BOOT_THREAD_START_CONTEXT_SIZE 40u
#define VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE 0x0001C000u
#define VC_APF_BOOT_FRONTIER_XAPI_THREAD_STARTUP 0x84BF2930u
#define VC_APF_BOOT_FRONTIER_THREAD_START_ADDRESS 0x84B57888u

/* The reached APF VM calls all select the Xenon 64 KiB virtual heap. */
#define VC_APF_BOOT_VM_PAGE_SIZE 0x00010000u
#define VC_APF_BOOT_VM_MAX_PAGES 16384u
#define VC_APF_BOOT_VM_MAX_ALLOCATIONS 256u
#define VC_APF_BOOT_VM_MAX_EXISTING_RANGES 16u
#define VC_APF_MEMORY_BASIC_INFORMATION_SIZE 28u
#define VC_APF_RETAIL_TITLE_BASE 0x82000000u
#define VC_APF_RETAIL_TITLE_SIZE 0x03380000u
#define VC_APF_STATIC_DISPATCH_BASE 0x85380000u
#define VC_APF_STATIC_DISPATCH_SIZE 0x00DB3000u
#define VC_APF_RETAIL_IMPORT_THUNK_BASE 0x84D07B6Cu
#define VC_APF_RETAIL_IMPORT_THUNK_SPAN 0x000014D4u

/* Exact Xbox 360 values needed by the bounded VM import group. */
#define VC_APF_X_STATUS_SUCCESS 0x00000000u
#define VC_APF_X_STATUS_TIMEOUT 0x00000102u
#define VC_APF_X_STATUS_OBJECT_NAME_EXISTS 0x40000000u
#define VC_APF_X_STATUS_UNSUCCESSFUL 0xC0000001u
#define VC_APF_X_STATUS_INVALID_HANDLE 0xC0000008u
#define VC_APF_X_STATUS_INVALID_PARAMETER 0xC000000Du
#define VC_APF_X_STATUS_NO_MEMORY 0xC0000017u
#define VC_APF_X_STATUS_MEMORY_NOT_ALLOCATED 0xC00000A0u
#define VC_APF_X_ERROR_INVALID_HANDLE 0x00000006u
#define VC_APF_X_ERROR_NOT_ENOUGH_MEMORY 0x00000008u
#define VC_APF_X_ERROR_IO_PENDING 0x000003E5u
#define VC_APF_X_MEM_COMMIT 0x00001000u
#define VC_APF_X_MEM_RESERVE 0x00002000u
#define VC_APF_X_MEM_DECOMMIT 0x00004000u
#define VC_APF_X_MEM_RELEASE 0x00008000u
#define VC_APF_X_MEM_FREE 0x00010000u
#define VC_APF_X_MEM_PRIVATE 0x00020000u
#define VC_APF_X_MEM_NOZERO 0x00800000u
#define VC_APF_X_MEM_LARGE_PAGES 0x20000000u
#define VC_APF_X_MEM_HEAP 0x40000000u
#define VC_APF_X_PAGE_READWRITE 0x00000004u

#define VC_APF_BOOT_CONFIG_PROCESS_TYPE (1u << 0)
#define VC_APF_BOOT_CONFIG_LANGUAGE (1u << 1)
#define VC_APF_BOOT_CONFIG_AV_PACK (1u << 2)
#define VC_APF_BOOT_CONFIG_SYSTEM_FLAGS (1u << 3)
#define VC_APF_BOOT_CONFIG_SECURED_AV_REGION (1u << 4)
#define VC_APF_BOOT_CONFIG_USER_VIDEO_FLAGS (1u << 5)
#define VC_APF_BOOT_CONFIG_VIRTUAL_MEMORY (1u << 6)
#define VC_APF_BOOT_CONFIG_ALL                                              \
    (VC_APF_BOOT_CONFIG_PROCESS_TYPE | VC_APF_BOOT_CONFIG_LANGUAGE |        \
     VC_APF_BOOT_CONFIG_AV_PACK | VC_APF_BOOT_CONFIG_SYSTEM_FLAGS |         \
     VC_APF_BOOT_CONFIG_SECURED_AV_REGION |                                 \
     VC_APF_BOOT_CONFIG_USER_VIDEO_FLAGS |                                  \
     VC_APF_BOOT_CONFIG_VIRTUAL_MEMORY)

/* Exact APF callable-import thunk addresses from default.xex. */
#define VC_APF_THUNK_XGET_LANGUAGE 0x84D07EECu
#define VC_APF_THUNK_XGET_AV_PACK 0x84D07EFCu
#define VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION 0x84D07FBCu
#define VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION 0x84D07FCCu
#define VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION 0x84D07FDCu
#define VC_APF_THUNK_XAM_LOADER_TERMINATE_TITLE 0x84D07F0Cu
#define VC_APF_THUNK_RTL_INIT_ANSI_STRING 0x84D0831Cu
#define VC_APF_THUNK_KE_BUG_CHECK 0x84D0833Cu
#define VC_APF_THUNK_NT_CREATE_EVENT 0x84D0839Cu
#define VC_APF_THUNK_NT_CLOSE 0x84D083ACu
#define VC_APF_THUNK_EX_GET_XCONFIG_SETTING 0x84D081ECu
#define VC_APF_THUNK_DBG_PRINT 0x84D081BCu
#define VC_APF_THUNK_KE_TLS_ALLOC 0x84D0834Cu
#define VC_APF_THUNK_KE_TLS_GET_VALUE 0x84D0835Cu
#define VC_APF_THUNK_KE_TLS_SET_VALUE 0x84D0836Cu
#define VC_APF_THUNK_KE_TLS_FREE 0x84D0837Cu
#define VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE 0x84D0852Cu
#define VC_APF_THUNK_KE_BUG_CHECK_EX 0x84D0867Cu
#define VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE 0x84D0868Cu
#define VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG 0x84D0869Cu
#define VC_APF_THUNK_RTL_RAISE_EXCEPTION 0x84D086CCu
#define VC_APF_THUNK_EX_CREATE_THREAD 0x84D0876Cu
#define VC_APF_THUNK_HAL_RETURN_TO_FIRMWARE 0x84D087ACu
#define VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD 0x84D0859Cu
#define VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY 0x84D0863Cu
#define VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY 0x84D085ECu
#define VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY 0x84D086BCu
#define VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX 0x84D084ECu
#define VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR 0x84D0864Cu
#define VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX 0x84D07EDCu

#define VC_APF_ANSI_STRING_SIZE 8u
#define VC_APF_OBJECT_ATTRIBUTES_SIZE 12u
#define VC_APF_RTL_CRITICAL_SECTION_SIZE 28u
#define VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS 0x844D37B8u
#define VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_SIZE 24u
#define VC_APF_XEX_HEADER_DEFAULT_HEAP_SIZE 0x00020401u
#define VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT 15u
#define VC_APF_RETAIL_XEX_PREFIX_SIZE                                      \
    (24u + VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT * 8u)

typedef enum vc_apf_boot_leaf_status {
    VC_APF_BOOT_LEAF_OK = 0,
    VC_APF_BOOT_LEAF_INVALID_ARGUMENT,
    VC_APF_BOOT_LEAF_CONFIG_REQUIRED,
    VC_APF_BOOT_LEAF_THREAD_REQUIRED,
    VC_APF_BOOT_LEAF_THREAD_CAPACITY,
    VC_APF_BOOT_LEAF_MEMORY_FAULT,
    VC_APF_BOOT_LEAF_GUEST_STATE,
    VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED,
    VC_APF_BOOT_LEAF_UI_REQUESTED,
    VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED,
    VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT,
    VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED,
    VC_APF_BOOT_LEAF_TERMINAL_OUTCOME,
    VC_APF_BOOT_LEAF_UNSUPPORTED_IMPORT,
    VC_APF_BOOT_LEAF_UNKNOWN_IMPORT
} vc_apf_boot_leaf_status;

typedef enum vc_apf_boot_vm_existing_range_kind {
    VC_APF_BOOT_VM_RANGE_TITLE_IMAGE = 1,
    VC_APF_BOOT_VM_RANGE_STATIC_DISPATCH,
    VC_APF_BOOT_VM_RANGE_IMPORT_THUNKS,
    VC_APF_BOOT_VM_RANGE_OTHER_MAPPING
} vc_apf_boot_vm_existing_range_kind;

typedef struct vc_apf_boot_vm_existing_range {
    uint32_t guest_base;
    uint32_t byte_count;
    vc_apf_boot_vm_existing_range_kind kind;
} vc_apf_boot_vm_existing_range;

typedef struct vc_apf_boot_leaf_config {
    /* All seven bits in configured_fields are mandatory; there are no defaults. */
    uint32_t configured_fields;
    uint32_t process_type;
    uint32_t language;
    uint32_t av_pack;
    uint32_t executable_system_flags;
    uint32_t secured_av_region;
    uint32_t user_video_flags;
    /*
     * Loader-owned writable backing and a collision policy for the exact
     * 64 KiB guest virtual heap reached before main. The backing must remain
     * alive for the runtime lifetime and must contain exactly vm_arena_size
     * bytes. TITLE_IMAGE, STATIC_DISPATCH, and IMPORT_THUNKS ranges must cover
     * the exact APF constants above; the arena must be disjoint from all three
     * kinds.
     */
    uint32_t vm_arena_base;
    uint32_t vm_arena_size;
    uint8_t *vm_backing_bytes;
    size_t vm_backing_byte_count;
    size_t vm_existing_range_count;
    vc_apf_boot_vm_existing_range
        vm_existing_ranges[VC_APF_BOOT_VM_MAX_EXISTING_RANGES];
} vc_apf_boot_leaf_config;

typedef struct vc_apf_boot_vm_page {
    uint16_t allocation_id;
    uint8_t state;
    uint8_t protect;
} vc_apf_boot_vm_page;

typedef struct vc_apf_boot_vm_allocation {
    uint32_t base_page;
    uint32_t page_count;
    uint32_t allocation_protect;
    bool active;
} vc_apf_boot_vm_allocation;

typedef struct vc_apf_boot_event {
    uint32_t handle;
    uint32_t handle_ref_count;
    uint16_t name_length;
    bool active;
    bool manual_reset;
    bool signaled;
    bool named;
    uint8_t name[VC_APF_BOOT_EVENT_NAME_MAX + 1u];
} vc_apf_boot_event;

typedef struct vc_apf_guest_ppc_context {
    /*
     * Xenon integer ABI arguments use r3, r4, ...; 32-bit integer results
     * are sign-extended through all 64 bits of r3, matching the pinned Xenia
     * export-shim convention.
     */
    uint64_t gpr[32];
    uint32_t lr;
} vc_apf_guest_ppc_context;

typedef struct vc_apf_guest_memory {
    uint8_t *bytes;
    uint32_t guest_base;
    size_t byte_count;
} vc_apf_guest_memory;

struct vc_apf_boot_leaf_runtime;

typedef struct vc_apf_guest_thread {
    struct vc_apf_boot_leaf_runtime *owner;
    uint32_t initialized_cookie;
    /* Guest PKTHREAD/object address stored in RTL_CRITICAL_SECTION + 0x18. */
    uint32_t guest_thread_object;
    bool scheduler_blocked;
    uint32_t blocked_import_thunk;
    uint32_t blocked_guest_address;
    uint32_t blocked_return_address;
    uint32_t blocked_owner_guest_thread;
    bool ui_requested;
    uint32_t ui_request_id;
    vc_apf_guest_ppc_context ui_context;
    bool thread_create_requested;
    uint32_t thread_create_request_id;
    vc_apf_guest_ppc_context thread_create_context;
    bool exception_required;
    uint32_t exception_import_thunk;
    uint32_t exception_record;
    uint32_t exception_return_address;
    vc_apf_guest_ppc_context exception_context;
    uint32_t tls_values[VC_APF_BOOT_TLS_SLOT_COUNT];
} vc_apf_guest_thread;

typedef enum vc_apf_boot_terminal_outcome {
    VC_APF_BOOT_TERMINAL_NONE = 0,
    VC_APF_BOOT_TERMINAL_FIRMWARE_RETURN,
    VC_APF_BOOT_TERMINAL_BUGCHECK,
    VC_APF_BOOT_TERMINAL_TITLE_TERMINATE
} vc_apf_boot_terminal_outcome;

typedef struct vc_apf_boot_leaf_failure {
    vc_apf_boot_leaf_status status;
    uint32_t import_thunk;
    uint32_t guest_return_address;
    uint32_t guest_call_address;
    uint32_t guest_arguments[5];
    uint32_t related_guest_address;
    uint32_t owning_guest_thread;
    vc_apf_boot_terminal_outcome terminal_outcome;
} vc_apf_boot_leaf_failure;

typedef enum vc_apf_boot_debug_event_kind {
    VC_APF_BOOT_DEBUG_EVENT_NONE = 0,
    VC_APF_BOOT_DEBUG_EVENT_XAPI_RETURN_VALUE_S32
} vc_apf_boot_debug_event_kind;

/* Structured output from the sole proved DbgPrint variant; never host printf. */
typedef struct vc_apf_boot_debug_event {
    bool valid;
    vc_apf_boot_debug_event_kind kind;
    uint32_t import_thunk;
    uint32_t guest_call_address;
    uint32_t guest_return_address;
    uint32_t guest_format_address;
    uint32_t raw_value;
    int32_t signed_decimal_value;
} vc_apf_boot_debug_event;

/*
 * One host-visible request for APF's exact one-button UIEx call. UTF-16 code
 * units are host-endian and NUL-terminated. No button is selected implicitly.
 */
typedef struct vc_apf_boot_message_box_request {
    bool active;
    uint32_t request_id;
    uint32_t requesting_guest_thread;
    uint32_t import_thunk;
    uint32_t guest_call_address;
    uint32_t guest_return_address;
    uint32_t user_index;
    uint32_t button_count;
    uint32_t active_button;
    uint32_t flags;
    uint32_t opaque_r10_argument;
    uint32_t result_address;
    uint32_t overlapped_address;
    uint32_t event_handle;
    uint16_t message_length;
    uint16_t button_length;
    uint16_t message[VC_APF_BOOT_UI_MESSAGE_MAX_CODE_UNITS + 1u];
    uint16_t button[VC_APF_BOOT_UI_BUTTON_MAX_CODE_UNITS + 1u];
} vc_apf_boot_message_box_request;

/*
 * Non-resumable scheduler handoff for the exact frontier ExCreateThread call.
 * This is evidence, not a created thread: no handle, guest object, stack, TLS,
 * PCR, or runnable task exists until a future scheduler owns the lifecycle.
 */
typedef struct vc_apf_boot_thread_create_request {
    bool active;
    uint32_t request_id;
    uint32_t requesting_guest_thread;
    uint32_t import_thunk;
    uint32_t guest_call_address;
    uint32_t guest_return_address;
    uint32_t handle_address;
    uint32_t requested_stack_size;
    uint32_t effective_stack_size;
    uint32_t thread_id_address;
    uint32_t xapi_thread_startup;
    uint32_t start_address;
    uint32_t start_context;
    uint32_t creation_flags;
    bool create_suspended;
    uint8_t processor_affinity_mask;
} vc_apf_boot_thread_create_request;

typedef struct vc_apf_boot_leaf_runtime {
    uint32_t initialized_cookie;
    vc_apf_boot_leaf_config config;
    uint8_t tls_allocated[VC_APF_BOOT_TLS_SLOT_COUNT];
    vc_apf_guest_thread *threads[VC_APF_BOOT_MAX_GUEST_THREADS];
    size_t thread_count;
    vc_apf_boot_leaf_failure last_failure;
    vc_apf_boot_debug_event last_debug_event;
    uint32_t next_ui_request_id;
    vc_apf_boot_message_box_request pending_message_box;
    uint32_t next_thread_create_request_id;
    vc_apf_boot_thread_create_request pending_thread_create;
    size_t vm_page_count;
    size_t vm_allocation_count;
    vc_apf_boot_vm_page vm_pages[VC_APF_BOOT_VM_MAX_PAGES];
    vc_apf_boot_vm_allocation
        vm_allocations[VC_APF_BOOT_VM_MAX_ALLOCATIONS];
    size_t event_count;
    vc_apf_boot_event events[VC_APF_BOOT_MAX_EVENT_HANDLES];
} vc_apf_boot_leaf_runtime;

vc_apf_boot_leaf_status vc_apf_boot_leaf_runtime_init(
    vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_boot_leaf_config *config);

void vc_apf_boot_leaf_thread_init(vc_apf_guest_thread *thread);

vc_apf_boot_leaf_status vc_apf_boot_leaf_thread_attach(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    uint32_t guest_thread_object);

vc_apf_boot_leaf_status vc_apf_boot_leaf_thread_detach(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread);

/*
 * Complete the pending one-button request after the host user explicitly
 * selects button zero. On success, resume_context is the exact post-import
 * Xenon context (r3 = X_ERROR_IO_PENDING). No other selection is invented.
 */
vc_apf_boot_leaf_status vc_apf_boot_leaf_complete_message_box_ui(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    const vc_apf_guest_memory *memory,
    uint32_t request_id,
    uint32_t selected_button,
    vc_apf_guest_ppc_context *resume_context);

/*
 * Dispatch one exact APF import thunk using r3/r4/r5 as the Xenon ABI inputs.
 * Any status other than VC_APF_BOOT_LEAF_OK stops immediate guest continuation.
 * SCHEDULER_BLOCKED requires a future park/wake implementation; UI_REQUESTED
 * requires explicit host completion through the function above;
 * THREAD_CREATE_REQUESTED has no completion API until a scheduler owns guest
 * object/handle, stack/TLS/PCR, runnable-state, exit, close, and teardown;
 * EXCEPTION_REQUIRED requires guest SEH dispatch/unwind; TERMINAL_OUTCOME never
 * resumes. The current scaffold must not resume generated title code for any of
 * those statuses.
 */
vc_apf_boot_leaf_status vc_apf_boot_leaf_dispatch(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *current_thread,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk);

const char *vc_apf_boot_leaf_status_name(vc_apf_boot_leaf_status status);

#ifdef __cplusplus
}
#endif

#endif
