#include "static_runtime/apf_boot_leaf_adapters.h"

#include <string.h>

#define VC_APF_BOOT_LEAF_COOKIE 0x4150464Cu /* "APFL" */
#define VC_APF_BOOT_THREAD_COOKIE 0x41504654u /* "APFT" */
#define VC_APF_VM_PAGE_FREE 0u
#define VC_APF_VM_PAGE_RESERVE 1u
#define VC_APF_VM_PAGE_COMMIT 2u
#define VC_APF_VM_PAGE_EXTERNAL 0x80u

static const char vc_apf_dbg_print_xapi_return_format[] =
    "[XAPI RETURN VALUE] %d\n";

typedef struct vc_apf_retail_xex_option {
    uint32_t key;
    uint32_t value_or_offset;
} vc_apf_retail_xex_option;

static const vc_apf_retail_xex_option vc_apf_retail_xex_options[] = {
    {0x000002FFu, 0x00004F54u}, {0x000003FFu, 0x00004F68u},
    {0x00010100u, 0x84BE9D08u}, {0x00010201u, 0x82000000u},
    {0x000103FFu, 0x000064E8u}, {0x00018002u, 0x00004F8Cu},
    {0x000183FFu, 0x00004F94u}, {0x000200FFu, 0x00004FBCu},
    {0x00020104u, 0x00005070u}, {0x00020200u, 0x00200000u},
    {0x00030000u, 0x00000200u}, {0x00040006u, 0x00005080u},
    {0x00040310u, 0x00005098u}, {0x00040404u, 0x000050D8u},
    {0x000405FFu, 0x000050E8u},
};

_Static_assert(sizeof(vc_apf_dbg_print_xapi_return_format) ==
                   VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_SIZE,
               "APF DbgPrint format size changed");
_Static_assert(sizeof(vc_apf_retail_xex_options) /
                       sizeof(vc_apf_retail_xex_options[0]) ==
                   VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT,
               "APF retail XEX option count changed");
_Static_assert(VC_APF_BOOT_VM_MAX_ALLOCATIONS < UINT16_MAX,
               "APF VM allocation identifiers must fit in uint16_t");
_Static_assert(VC_APF_BOOT_FIRST_EVENT_HANDLE >
                   VC_APF_STATIC_DISPATCH_BASE + VC_APF_STATIC_DISPATCH_SIZE,
               "APF event handles must not overlap title/dispatch addresses");
_Static_assert(VC_APF_BOOT_FIRST_EVENT_HANDLE >
                   VC_APF_RETAIL_IMPORT_THUNK_BASE +
                       VC_APF_RETAIL_IMPORT_THUNK_SPAN,
               "APF event handles must not overlap callable import thunks");
_Static_assert(VC_APF_BOOT_MAX_EVENT_HANDLES <=
                   (UINT32_MAX - VC_APF_BOOT_FIRST_EVENT_HANDLE) / 4u + 1u,
               "APF event handle range must fit in guest u32");
_Static_assert(VC_APF_XAM_OVERLAPPED_SIZE == 7u * sizeof(uint32_t),
               "XAM_OVERLAPPED must contain seven guest dwords");

static uint32_t vc_apf_gpr_u32(const vc_apf_guest_ppc_context *context,
                               unsigned int index) {
    return (uint32_t)context->gpr[index];
}

static void vc_apf_set_r3(vc_apf_guest_ppc_context *context, uint32_t value) {
    context->gpr[3] = (uint64_t)(int64_t)(int32_t)value;
}

static uint32_t vc_apf_failure_call_address(
    const vc_apf_guest_ppc_context *context,
    uint32_t import_thunk) {
    if (context == NULL) {
        return 0u;
    }

    /* The bounded frontier reaches both imports through non-linking tails. */
    if (import_thunk == VC_APF_THUNK_KE_BUG_CHECK) {
        return 0x84BDAA24u;
    }
    if (import_thunk == VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION &&
        context->lr == 0x84BD7C9Cu) {
        /* sub_84BD7C8C bl -> sub_84BDAA30 tail -> sub_84BDE0B0 tail. */
        return 0x84BDE0C0u;
    }

    return context->lr >= 4u ? context->lr - 4u : 0u;
}

static bool vc_apf_runtime_ready(const vc_apf_boot_leaf_runtime *runtime) {
    return runtime != NULL &&
           runtime->initialized_cookie == VC_APF_BOOT_LEAF_COOKIE;
}

static bool vc_apf_current_thread_ready(
    const vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_thread *thread) {
    size_t index;

    if (thread == NULL || thread->initialized_cookie != VC_APF_BOOT_THREAD_COOKIE ||
        thread->owner != runtime) {
        return false;
    }
    for (index = 0u; index < runtime->thread_count; ++index) {
        if (runtime->threads[index] == thread) {
            return true;
        }
    }
    return false;
}

static vc_apf_boot_leaf_status vc_apf_record_failure(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk,
    vc_apf_boot_leaf_status status) {
    size_t argument_index;

    if (runtime != NULL) {
        memset(&runtime->last_failure, 0, sizeof(runtime->last_failure));
        runtime->last_failure.status = status;
        runtime->last_failure.import_thunk = import_thunk;
        runtime->last_failure.guest_return_address =
            context != NULL ? context->lr : 0u;
        runtime->last_failure.guest_call_address =
            vc_apf_failure_call_address(context, import_thunk);
        if (context != NULL) {
            for (argument_index = 0u; argument_index < 5u;
                 ++argument_index) {
                runtime->last_failure.guest_arguments[argument_index] =
                    vc_apf_gpr_u32(context, (unsigned int)argument_index + 3u);
            }
        }
    }
    if (context != NULL) {
        vc_apf_set_r3(context, 0u);
    }
    return status;
}

static void vc_apf_clear_failure(vc_apf_boot_leaf_runtime *runtime) {
    memset(&runtime->last_failure, 0, sizeof(runtime->last_failure));
    runtime->last_failure.status = VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_record_terminal(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk,
    vc_apf_boot_terminal_outcome outcome) {
    (void)vc_apf_record_failure(runtime, context, import_thunk,
                                VC_APF_BOOT_LEAF_TERMINAL_OUTCOME);
    runtime->last_failure.terminal_outcome = outcome;
    return VC_APF_BOOT_LEAF_TERMINAL_OUTCOME;
}

static void vc_apf_clear_scheduler_block(vc_apf_guest_thread *thread) {
    thread->scheduler_blocked = false;
    thread->blocked_import_thunk = 0u;
    thread->blocked_guest_address = 0u;
    thread->blocked_return_address = 0u;
    thread->blocked_owner_guest_thread = 0u;
}

static void vc_apf_clear_thread_ui_request(vc_apf_guest_thread *thread) {
    thread->ui_requested = false;
    thread->ui_request_id = 0u;
    memset(&thread->ui_context, 0, sizeof(thread->ui_context));
}

static void vc_apf_clear_runtime_ui_request(
    vc_apf_boot_leaf_runtime *runtime) {
    memset(&runtime->pending_message_box, 0,
           sizeof(runtime->pending_message_box));
}

static void vc_apf_clear_thread_create_request(
    vc_apf_guest_thread *thread) {
    thread->thread_create_requested = false;
    thread->thread_create_request_id = 0u;
    memset(&thread->thread_create_context, 0,
           sizeof(thread->thread_create_context));
}

static void vc_apf_clear_runtime_thread_create_request(
    vc_apf_boot_leaf_runtime *runtime) {
    memset(&runtime->pending_thread_create, 0,
           sizeof(runtime->pending_thread_create));
}

static vc_apf_boot_leaf_status vc_apf_record_scheduler_block(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk,
    uint32_t related_guest_address,
    uint32_t owning_guest_thread) {
    const uint32_t return_address = context->lr;

    (void)vc_apf_record_failure(runtime, context, import_thunk,
                                VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED);
    runtime->last_failure.related_guest_address = related_guest_address;
    runtime->last_failure.owning_guest_thread = owning_guest_thread;
    vc_apf_set_r3(context, related_guest_address);
    thread->scheduler_blocked = true;
    thread->blocked_import_thunk = import_thunk;
    thread->blocked_guest_address = related_guest_address;
    thread->blocked_return_address = return_address;
    thread->blocked_owner_guest_thread = owning_guest_thread;
    return VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED;
}

static vc_apf_boot_leaf_status vc_apf_record_exception_required(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk) {
    const vc_apf_guest_ppc_context preserved_context = *context;

    (void)vc_apf_record_failure(runtime, context, import_thunk,
                                VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED);
    *context = preserved_context;
    thread->exception_required = true;
    thread->exception_import_thunk = import_thunk;
    thread->exception_record = vc_apf_gpr_u32(&preserved_context, 3u);
    thread->exception_return_address = preserved_context.lr;
    thread->exception_context = preserved_context;
    return VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED;
}

static vc_apf_boot_leaf_status vc_apf_ke_tls_alloc(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *current_thread,
    vc_apf_guest_ppc_context *context) {
    uint32_t slot;

    (void)current_thread;
    for (slot = 0u; slot < VC_APF_BOOT_TLS_SLOT_COUNT; ++slot) {
        if (runtime->tls_allocated[slot] == 0u) {
            size_t thread_index;
            runtime->tls_allocated[slot] = 1u;
            for (thread_index = 0u; thread_index < runtime->thread_count;
                 ++thread_index) {
                runtime->threads[thread_index]->tls_values[slot] = 0u;
            }
            vc_apf_set_r3(context, slot);
            return VC_APF_BOOT_LEAF_OK;
        }
    }

    vc_apf_set_r3(context, VC_APF_BOOT_TLS_OUT_OF_INDEXES);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_ke_tls_free(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_ppc_context *context) {
    const uint32_t slot = vc_apf_gpr_u32(context, 3u);
    size_t thread_index;

    if (slot == VC_APF_BOOT_TLS_OUT_OF_INDEXES ||
        slot >= VC_APF_BOOT_TLS_SLOT_COUNT ||
        runtime->tls_allocated[slot] == 0u) {
        vc_apf_set_r3(context, 0u);
        return VC_APF_BOOT_LEAF_OK;
    }

    for (thread_index = 0u; thread_index < runtime->thread_count;
         ++thread_index) {
        runtime->threads[thread_index]->tls_values[slot] = 0u;
    }
    runtime->tls_allocated[slot] = 0u;
    vc_apf_set_r3(context, 1u);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_ke_tls_get_value(
    const vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_thread *current_thread,
    vc_apf_guest_ppc_context *context) {
    const uint32_t slot = vc_apf_gpr_u32(context, 3u);

    if (slot >= VC_APF_BOOT_TLS_SLOT_COUNT ||
        runtime->tls_allocated[slot] == 0u) {
        vc_apf_set_r3(context, 0u);
    } else {
        vc_apf_set_r3(context, current_thread->tls_values[slot]);
    }
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_ke_tls_set_value(
    const vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *current_thread,
    vc_apf_guest_ppc_context *context) {
    const uint32_t slot = vc_apf_gpr_u32(context, 3u);
    const uint32_t value = vc_apf_gpr_u32(context, 4u);

    if (slot >= VC_APF_BOOT_TLS_SLOT_COUNT ||
        runtime->tls_allocated[slot] == 0u) {
        vc_apf_set_r3(context, 0u);
    } else {
        current_thread->tls_values[slot] = value;
        vc_apf_set_r3(context, 1u);
    }
    return VC_APF_BOOT_LEAF_OK;
}

static bool vc_apf_guest_span(const vc_apf_guest_memory *memory,
                              uint32_t guest_address,
                              uint32_t length,
                              uint8_t **bytes_out) {
    uint64_t offset;

    if (memory == NULL || bytes_out == NULL ||
        (memory->bytes == NULL && memory->byte_count != 0u) ||
        guest_address < memory->guest_base ||
        (uint64_t)guest_address + (uint64_t)length >
            (uint64_t)UINT32_MAX + 1u) {
        return false;
    }
    offset = (uint64_t)guest_address - (uint64_t)memory->guest_base;
    if (offset > (uint64_t)memory->byte_count ||
        (uint64_t)length > (uint64_t)memory->byte_count - offset) {
        return false;
    }
    *bytes_out = memory->bytes + (size_t)offset;
    return true;
}

static uint32_t vc_apf_load_be_u32(const uint8_t *bytes) {
    return ((uint32_t)bytes[0] << 24u) | ((uint32_t)bytes[1] << 16u) |
           ((uint32_t)bytes[2] << 8u) | (uint32_t)bytes[3];
}

static uint16_t vc_apf_load_be_u16(const uint8_t *bytes) {
    return (uint16_t)(((uint16_t)bytes[0] << 8u) | (uint16_t)bytes[1]);
}

static uint64_t vc_apf_load_be_u64(const uint8_t *bytes) {
    return ((uint64_t)vc_apf_load_be_u32(bytes) << 32u) |
           (uint64_t)vc_apf_load_be_u32(bytes + 4u);
}

static int32_t vc_apf_load_be_s32(const uint8_t *bytes) {
    return (int32_t)vc_apf_load_be_u32(bytes);
}

static void vc_apf_store_be_u16(uint8_t *bytes, uint16_t value) {
    bytes[0] = (uint8_t)(value >> 8u);
    bytes[1] = (uint8_t)value;
}

static void vc_apf_store_be_u32(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)(value >> 24u);
    bytes[1] = (uint8_t)(value >> 16u);
    bytes[2] = (uint8_t)(value >> 8u);
    bytes[3] = (uint8_t)value;
}

static bool vc_apf_spans_overlap(uint32_t first_address,
                                 uint32_t first_length,
                                 uint32_t second_address,
                                 uint32_t second_length) {
    const uint64_t first_end = (uint64_t)first_address + first_length;
    const uint64_t second_end = (uint64_t)second_address + second_length;
    return (uint64_t)first_address < second_end &&
           (uint64_t)second_address < first_end;
}

static bool vc_apf_guest_c_string_length(const vc_apf_guest_memory *memory,
                                         uint32_t guest_address,
                                         size_t *length_out) {
    uint64_t offset;
    uint64_t memory_available;
    uint64_t guest_available;
    size_t available;
    const uint8_t *terminator;

    if (memory == NULL || length_out == NULL || memory->bytes == NULL ||
        guest_address == 0u || guest_address < memory->guest_base) {
        return false;
    }
    offset = (uint64_t)guest_address - (uint64_t)memory->guest_base;
    if (offset >= (uint64_t)memory->byte_count) {
        return false;
    }
    memory_available = (uint64_t)memory->byte_count - offset;
    guest_available = (uint64_t)UINT32_MAX + 1u - guest_address;
    available = (size_t)(memory_available < guest_available
                             ? memory_available
                             : guest_available);
    terminator = memchr(memory->bytes + (size_t)offset, 0, available);
    if (terminator == NULL) {
        return false;
    }
    *length_out = (size_t)(terminator - (memory->bytes + (size_t)offset));
    return true;
}

typedef struct vc_apf_event_name_candidate {
    bool present;
    uint16_t length;
    uint8_t bytes[VC_APF_BOOT_EVENT_NAME_MAX + 1u];
} vc_apf_event_name_candidate;

static uint8_t vc_apf_ascii_fold(uint8_t value) {
    if (value >= (uint8_t)'A' && value <= (uint8_t)'Z') {
        return (uint8_t)(value + ((uint8_t)'a' - (uint8_t)'A'));
    }
    return value;
}

static bool vc_apf_event_names_equal(
    const vc_apf_boot_event *event,
    const vc_apf_event_name_candidate *candidate) {
    size_t index;

    if (!event->named || !candidate->present ||
        event->name_length != candidate->length) {
        return false;
    }
    for (index = 0u; index < candidate->length; ++index) {
        if (vc_apf_ascii_fold(event->name[index]) !=
            vc_apf_ascii_fold(candidate->bytes[index])) {
            return false;
        }
    }
    return true;
}

static vc_apf_boot_leaf_status vc_apf_load_event_name(
    const vc_apf_guest_memory *memory,
    uint32_t object_attributes_address,
    vc_apf_event_name_candidate *candidate) {
    uint8_t *attributes;
    uint8_t *ansi_string;
    uint8_t *name;
    uint32_t ansi_string_address;
    uint32_t name_address;
    uint16_t length;
    uint16_t maximum_length;

    memset(candidate, 0, sizeof(*candidate));
    if (object_attributes_address == 0u) {
        return VC_APF_BOOT_LEAF_OK;
    }
    if ((object_attributes_address & 3u) != 0u ||
        !vc_apf_guest_span(memory, object_attributes_address,
                           VC_APF_OBJECT_ATTRIBUTES_SIZE, &attributes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }

    ansi_string_address = vc_apf_load_be_u32(attributes + 4u);
    if (vc_apf_load_be_u32(attributes) != UINT32_C(0xFFFFFFFC) ||
        vc_apf_load_be_u32(attributes + 8u) != UINT32_C(0x00000080) ||
        ansi_string_address == 0u || (ansi_string_address & 3u) != 0u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, ansi_string_address,
                           VC_APF_ANSI_STRING_SIZE, &ansi_string)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    length = vc_apf_load_be_u16(ansi_string);
    maximum_length = vc_apf_load_be_u16(ansi_string + 2u);
    name_address = vc_apf_load_be_u32(ansi_string + 4u);
    if (length > VC_APF_BOOT_EVENT_NAME_MAX || maximum_length == 0u ||
        maximum_length != (uint16_t)(length + 1u) || name_address == 0u) {
        /* PORTME at 0x84D0839C: retain longer/non-helper event-name forms. */
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, name_address,
                           (uint32_t)length + 1u, &name)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    if (name[length] != 0u) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }
    if (length == 0u) {
        return VC_APF_BOOT_LEAF_OK;
    }

    candidate->present = true;
    candidate->length = length;
    memcpy(candidate->bytes, name, (size_t)length + 1u);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_event *vc_apf_event_for_handle(
    vc_apf_boot_leaf_runtime *runtime,
    uint32_t handle) {
    uint32_t relative;
    size_t slot;

    if (handle < VC_APF_BOOT_FIRST_EVENT_HANDLE || (handle & 3u) != 0u) {
        return NULL;
    }
    relative = handle - VC_APF_BOOT_FIRST_EVENT_HANDLE;
    slot = (size_t)(relative / 4u);
    if (slot >= VC_APF_BOOT_MAX_EVENT_HANDLES ||
        !runtime->events[slot].active ||
        runtime->events[slot].handle != handle) {
        return NULL;
    }
    return &runtime->events[slot];
}

static vc_apf_boot_leaf_status vc_apf_nt_create_event(
    vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t handle_pointer = vc_apf_gpr_u32(context, 3u);
    const uint32_t object_attributes = vc_apf_gpr_u32(context, 4u);
    const uint32_t event_type = vc_apf_gpr_u32(context, 5u);
    const uint32_t initial_state = vc_apf_gpr_u32(context, 6u);
    vc_apf_event_name_candidate candidate;
    vc_apf_boot_leaf_status status;
    vc_apf_boot_event *event = NULL;
    uint8_t *handle_bytes;
    size_t slot;

    if (context->lr == 0x84BE708Cu) {
        if (event_type > 1u || initial_state > 1u) {
            return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
        }
    } else if (context->lr == 0x84BE9A30u) {
        if (object_attributes != 0u || event_type != 1u ||
            initial_state != 0u) {
            return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
        }
    } else {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (handle_pointer == 0u || (handle_pointer & 3u) != 0u ||
        !vc_apf_guest_span(memory, handle_pointer, 4u, &handle_bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    status = vc_apf_load_event_name(memory, object_attributes, &candidate);
    if (status != VC_APF_BOOT_LEAF_OK) {
        return status;
    }

    if (candidate.present) {
        for (slot = 0u; slot < VC_APF_BOOT_MAX_EVENT_HANDLES; ++slot) {
            if (vc_apf_event_names_equal(&runtime->events[slot],
                                         &candidate)) {
                event = &runtime->events[slot];
                break;
            }
        }
        if (event != NULL) {
            if (event->handle_ref_count == UINT32_MAX) {
                return VC_APF_BOOT_LEAF_GUEST_STATE;
            }
            ++event->handle_ref_count;
            vc_apf_store_be_u32(handle_bytes, event->handle);
            vc_apf_set_r3(context, VC_APF_X_STATUS_OBJECT_NAME_EXISTS);
            return VC_APF_BOOT_LEAF_OK;
        }
    }

    for (slot = 0u; slot < VC_APF_BOOT_MAX_EVENT_HANDLES; ++slot) {
        if (!runtime->events[slot].active) {
            event = &runtime->events[slot];
            break;
        }
    }
    if (event == NULL) {
        vc_apf_set_r3(context, VC_APF_X_STATUS_NO_MEMORY);
        return VC_APF_BOOT_LEAF_OK;
    }

    memset(event, 0, sizeof(*event));
    event->handle = VC_APF_BOOT_FIRST_EVENT_HANDLE + (uint32_t)slot * 4u;
    event->handle_ref_count = 1u;
    event->active = true;
    event->manual_reset = event_type == 0u;
    event->signaled = initial_state != 0u;
    event->named = candidate.present;
    event->name_length = candidate.length;
    if (candidate.present) {
        memcpy(event->name, candidate.bytes, (size_t)candidate.length + 1u);
    }
    ++runtime->event_count;
    vc_apf_store_be_u32(handle_bytes, event->handle);
    vc_apf_set_r3(context, VC_APF_X_STATUS_SUCCESS);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_nt_close(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_ppc_context *context) {
    vc_apf_boot_event *event;

    if (context->lr != 0x84BE9A90u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    event = vc_apf_event_for_handle(runtime, vc_apf_gpr_u32(context, 3u));
    if (event == NULL) {
        vc_apf_set_r3(context, VC_APF_X_STATUS_INVALID_HANDLE);
        return VC_APF_BOOT_LEAF_OK;
    }
    if (event->handle_ref_count > 1u) {
        --event->handle_ref_count;
    } else {
        /*
         * PORTME at 0x84D083AC: retain an object reference across a wait if a
         * different guest thread closes its final handle concurrently.
         */
        memset(event, 0, sizeof(*event));
        --runtime->event_count;
    }
    vc_apf_set_r3(context, VC_APF_X_STATUS_SUCCESS);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_nt_wait_for_single_object_ex(
    vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t handle = vc_apf_gpr_u32(context, 3u);
    const uint32_t wait_mode = vc_apf_gpr_u32(context, 4u);
    const uint32_t alertable = vc_apf_gpr_u32(context, 5u);
    const uint32_t timeout_pointer = vc_apf_gpr_u32(context, 6u);
    vc_apf_boot_event *event;
    int64_t timeout_ticks = -1;
    uint8_t *timeout_bytes;

    if (context->lr != 0x84BF0E40u || wait_mode != 1u || alertable > 1u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    event = vc_apf_event_for_handle(runtime, handle);
    if (event == NULL) {
        vc_apf_set_r3(context, VC_APF_X_STATUS_INVALID_HANDLE);
        return VC_APF_BOOT_LEAF_OK;
    }
    if (timeout_pointer != 0u) {
        if ((timeout_pointer & 7u) != 0u ||
            !vc_apf_guest_span(memory, timeout_pointer, 8u,
                               &timeout_bytes)) {
            return VC_APF_BOOT_LEAF_MEMORY_FAULT;
        }
        timeout_ticks = (int64_t)vc_apf_load_be_u64(timeout_bytes);
        if (timeout_ticks > 0) {
            /* The reached wrapper produces only NULL or relative timeouts. */
            return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
        }
    }

    if (event->signaled) {
        if (!event->manual_reset) {
            event->signaled = false;
        }
        vc_apf_set_r3(context, VC_APF_X_STATUS_SUCCESS);
        return VC_APF_BOOT_LEAF_OK;
    }
    if (timeout_pointer != 0u && timeout_ticks == 0) {
        vc_apf_set_r3(context, VC_APF_X_STATUS_TIMEOUT);
        return VC_APF_BOOT_LEAF_OK;
    }

    /*
     * PORTME at 0x84D084EC: register a scheduler deadline, APC wakeup, and
     * event signal wakeup. Never block the Linux host thread or invent time.
     */
    return VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED;
}

static vc_apf_boot_leaf_status vc_apf_load_ui_utf16z(
    const vc_apf_guest_memory *memory,
    uint32_t guest_address,
    uint32_t maximum_code_units,
    uint16_t *code_units_out,
    uint16_t *length_out) {
    uint8_t *bytes;
    uint32_t index;
    const uint32_t span_code_units = maximum_code_units + 1u;
    const uint32_t span_bytes = span_code_units * 2u;

    if (guest_address == 0u || (guest_address & 1u) != 0u ||
        code_units_out == NULL || length_out == NULL ||
        !vc_apf_guest_span(memory, guest_address, span_bytes, &bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    for (index = 0u; index < span_code_units; ++index) {
        const uint16_t code_unit =
            vc_apf_load_be_u16(bytes + (size_t)index * 2u);
        code_units_out[index] = code_unit;
        if (code_unit == 0u) {
            *length_out = (uint16_t)index;
            return VC_APF_BOOT_LEAF_OK;
        }
    }
    return VC_APF_BOOT_LEAF_GUEST_STATE;
}

static vc_apf_boot_leaf_status vc_apf_xam_show_message_box_ui_ex(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *current_thread,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t stack_pointer = vc_apf_gpr_u32(context, 1u);
    vc_apf_boot_message_box_request candidate;
    vc_apf_guest_ppc_context preserved_context;
    vc_apf_boot_event *event;
    vc_apf_boot_leaf_status status;
    uint8_t *stack_argument_9;
    uint8_t *stack_argument_10;
    uint8_t *button_pointer_cell;
    uint8_t *result_bytes;
    uint8_t *overlapped_bytes;
    uint32_t result_address;
    uint32_t overlapped_address;
    uint32_t button_address;
    uint32_t event_handle;
    uint32_t next_request_id;

    /*
     * PORTME at 0x84D07EDC: the extra UIEx r10 argument and eight-byte result
     * object remain semantically unnamed. This exact APF caller never reads
     * the result object, so the bounded adapter validates and preserves it.
     */
    if (context->lr != 0x84BE9A6Cu ||
        runtime->pending_message_box.active ||
        stack_pointer > UINT32_MAX - 432u ||
        (stack_pointer & 15u) != 0u ||
        vc_apf_gpr_u32(context, 3u) != 255u ||
        vc_apf_gpr_u32(context, 4u) != 0u ||
        vc_apf_gpr_u32(context, 5u) != stack_pointer + 432u ||
        vc_apf_gpr_u32(context, 6u) != 1u ||
        vc_apf_gpr_u32(context, 7u) != stack_pointer + 204u ||
        vc_apf_gpr_u32(context, 8u) != 0u ||
        vc_apf_gpr_u32(context, 9u) != 1u ||
        vc_apf_gpr_u32(context, 10u) != 1u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, stack_pointer + 84u, 4u,
                           &stack_argument_9) ||
        !vc_apf_guest_span(memory, stack_pointer + 92u, 4u,
                           &stack_argument_10) ||
        !vc_apf_guest_span(memory, stack_pointer + 204u, 4u,
                           &button_pointer_cell)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    result_address = vc_apf_load_be_u32(stack_argument_9);
    overlapped_address = vc_apf_load_be_u32(stack_argument_10);
    button_address = vc_apf_load_be_u32(button_pointer_cell);
    if (result_address != stack_pointer + 104u ||
        overlapped_address != stack_pointer + 112u ||
        button_address != stack_pointer + 368u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, result_address, 8u, &result_bytes) ||
        !vc_apf_guest_span(memory, overlapped_address,
                           VC_APF_XAM_OVERLAPPED_SIZE,
                           &overlapped_bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    event_handle = vc_apf_load_be_u32(overlapped_bytes + 12u);
    event = vc_apf_event_for_handle(runtime, event_handle);
    if (vc_apf_load_be_u32(result_bytes) != 0u ||
        vc_apf_load_be_u32(result_bytes + 4u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 4u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 8u) != 0u ||
        event == NULL || event->manual_reset || event->signaled ||
        vc_apf_load_be_u32(overlapped_bytes + 16u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 20u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 24u) != 0u) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }

    memset(&candidate, 0, sizeof(candidate));
    status = vc_apf_load_ui_utf16z(
        memory, stack_pointer + 432u,
        VC_APF_BOOT_UI_MESSAGE_MAX_CODE_UNITS, candidate.message,
        &candidate.message_length);
    if (status != VC_APF_BOOT_LEAF_OK) {
        return status;
    }
    status = vc_apf_load_ui_utf16z(
        memory, button_address, VC_APF_BOOT_UI_BUTTON_MAX_CODE_UNITS,
        candidate.button, &candidate.button_length);
    if (status != VC_APF_BOOT_LEAF_OK) {
        return status;
    }

    candidate.active = true;
    candidate.request_id = runtime->next_ui_request_id;
    candidate.requesting_guest_thread = current_thread->guest_thread_object;
    candidate.import_thunk = VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX;
    candidate.guest_call_address = 0x84BE9A68u;
    candidate.guest_return_address = 0x84BE9A6Cu;
    candidate.user_index = 255u;
    candidate.button_count = 1u;
    candidate.active_button = 0u;
    candidate.flags = 1u;
    candidate.opaque_r10_argument = 1u;
    candidate.result_address = result_address;
    candidate.overlapped_address = overlapped_address;
    candidate.event_handle = event_handle;

    next_request_id = candidate.request_id + 1u;
    if (next_request_id == 0u) {
        next_request_id = 1u;
    }
    preserved_context = *context;
    (void)vc_apf_record_failure(
        runtime, context, VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX,
        VC_APF_BOOT_LEAF_UI_REQUESTED);
    runtime->last_failure.related_guest_address = overlapped_address;
    runtime->last_failure.owning_guest_thread =
        current_thread->guest_thread_object;
    *context = preserved_context;
    vc_apf_set_r3(context, VC_APF_X_ERROR_IO_PENDING);
    vc_apf_store_be_u32(overlapped_bytes, VC_APF_X_ERROR_IO_PENDING);
    runtime->pending_message_box = candidate;
    runtime->next_ui_request_id = next_request_id;
    current_thread->ui_requested = true;
    current_thread->ui_request_id = candidate.request_id;
    current_thread->ui_context = *context;
    return VC_APF_BOOT_LEAF_UI_REQUESTED;
}

vc_apf_boot_leaf_status vc_apf_boot_leaf_complete_message_box_ui(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    const vc_apf_guest_memory *memory,
    uint32_t request_id,
    uint32_t selected_button,
    vc_apf_guest_ppc_context *resume_context) {
    const vc_apf_boot_message_box_request *request;
    vc_apf_guest_ppc_context completed_context;
    vc_apf_boot_event *event;
    uint8_t *result_bytes;
    uint8_t *overlapped_bytes;

    if (!vc_apf_runtime_ready(runtime)) {
        return VC_APF_BOOT_LEAF_CONFIG_REQUIRED;
    }
    if (!vc_apf_current_thread_ready(runtime, thread)) {
        return VC_APF_BOOT_LEAF_THREAD_REQUIRED;
    }
    if (resume_context == NULL) {
        return VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
    }
    request = &runtime->pending_message_box;
    if (!request->active || !thread->ui_requested ||
        thread->ui_request_id != request->request_id ||
        request->requesting_guest_thread != thread->guest_thread_object) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }
    if (request_id != request->request_id) {
        return VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
    }
    if (selected_button != 0u || request->button_count != 1u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, request->result_address, 8u,
                           &result_bytes) ||
        !vc_apf_guest_span(memory, request->overlapped_address,
                           VC_APF_XAM_OVERLAPPED_SIZE,
                           &overlapped_bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    event = vc_apf_event_for_handle(runtime, request->event_handle);
    if (vc_apf_load_be_u32(result_bytes) != 0u ||
        vc_apf_load_be_u32(result_bytes + 4u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes) !=
            VC_APF_X_ERROR_IO_PENDING ||
        vc_apf_load_be_u32(overlapped_bytes + 4u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 8u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 12u) !=
            request->event_handle ||
        event == NULL || event->manual_reset || event->signaled ||
        vc_apf_load_be_u32(overlapped_bytes + 16u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 20u) != 0u ||
        vc_apf_load_be_u32(overlapped_bytes + 24u) != 0u) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }

    completed_context = thread->ui_context;
    vc_apf_store_be_u32(overlapped_bytes, VC_APF_X_STATUS_SUCCESS);
    vc_apf_store_be_u32(overlapped_bytes + 4u, 0u);
    vc_apf_store_be_u32(overlapped_bytes + 24u, VC_APF_X_STATUS_SUCCESS);
    event->signaled = true;
    vc_apf_clear_thread_ui_request(thread);
    vc_apf_clear_runtime_ui_request(runtime);
    vc_apf_clear_failure(runtime);
    *resume_context = completed_context;
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_ex_create_thread_request(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *current_thread,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t stack_pointer = vc_apf_gpr_u32(context, 1u);
    const uint32_t start_context = vc_apf_gpr_u32(context, 8u);
    vc_apf_boot_thread_create_request candidate;
    vc_apf_guest_ppc_context preserved_context;
    uint8_t *handle_bytes;
    uint8_t *thread_id_bytes;
    uint8_t *start_context_bytes;
    uint32_t next_request_id;

    /*
     * PORTME at 0x84D0876C: a future scheduler must transactionally own an
     * X_KTHREAD-compatible guest object and handle, guarded guest stack,
     * per-thread TLS/PCR/CPU context, runnable/exit state, close references,
     * and teardown before this request can complete. Never create a detached
     * host thread, run 0x84B57888 synchronously, or fabricate NT success here.
     */
    if (context->lr != 0x84BF1090u ||
        runtime->pending_thread_create.active ||
        stack_pointer > UINT32_MAX - 176u ||
        (stack_pointer & 15u) != 0u ||
        vc_apf_gpr_u32(context, 3u) != stack_pointer + 80u ||
        vc_apf_gpr_u32(context, 4u) !=
            VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE ||
        vc_apf_gpr_u32(context, 5u) != stack_pointer + 176u ||
        vc_apf_gpr_u32(context, 6u) !=
            VC_APF_BOOT_FRONTIER_XAPI_THREAD_STARTUP ||
        vc_apf_gpr_u32(context, 7u) !=
            VC_APF_BOOT_FRONTIER_THREAD_START_ADDRESS ||
        start_context == 0u || (start_context & 3u) != 0u ||
        vc_apf_gpr_u32(context, 9u) != 0u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, stack_pointer + 80u, 4u,
                           &handle_bytes) ||
        !vc_apf_guest_span(memory, stack_pointer + 176u, 4u,
                           &thread_id_bytes) ||
        !vc_apf_guest_span(memory, start_context,
                           VC_APF_BOOT_THREAD_START_CONTEXT_SIZE,
                           &start_context_bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    (void)handle_bytes;
    (void)thread_id_bytes;
    if (vc_apf_spans_overlap(start_context,
                             VC_APF_BOOT_THREAD_START_CONTEXT_SIZE,
                             stack_pointer + 80u, 4u) ||
        vc_apf_spans_overlap(start_context,
                             VC_APF_BOOT_THREAD_START_CONTEXT_SIZE,
                             stack_pointer + 176u, 4u) ||
        vc_apf_load_be_u32(start_context_bytes + 0u) != 0x820046D4u ||
        vc_apf_load_be_u32(start_context_bytes + 4u) != UINT32_MAX ||
        vc_apf_load_be_u32(start_context_bytes + 8u) != 0x84502174u ||
        vc_apf_load_be_u32(start_context_bytes + 12u) != 0u ||
        vc_apf_load_be_u32(start_context_bytes + 16u) != start_context ||
        vc_apf_load_be_u32(start_context_bytes + 20u) != 0u ||
        vc_apf_load_be_u32(start_context_bytes + 24u) != start_context ||
        vc_apf_load_be_u32(start_context_bytes + 28u) != 0u ||
        vc_apf_load_be_u32(start_context_bytes + 32u) != 128u ||
        vc_apf_load_be_u32(start_context_bytes + 36u) != 0u) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }

    memset(&candidate, 0, sizeof(candidate));
    candidate.active = true;
    candidate.request_id = runtime->next_thread_create_request_id;
    candidate.requesting_guest_thread = current_thread->guest_thread_object;
    candidate.import_thunk = VC_APF_THUNK_EX_CREATE_THREAD;
    candidate.guest_call_address = 0x84BF108Cu;
    candidate.guest_return_address = 0x84BF1090u;
    candidate.handle_address = stack_pointer + 80u;
    candidate.requested_stack_size =
        VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE;
    candidate.effective_stack_size =
        VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE;
    candidate.thread_id_address = stack_pointer + 176u;
    candidate.xapi_thread_startup =
        VC_APF_BOOT_FRONTIER_XAPI_THREAD_STARTUP;
    candidate.start_address = VC_APF_BOOT_FRONTIER_THREAD_START_ADDRESS;
    candidate.start_context = start_context;
    candidate.creation_flags = 0u;
    candidate.create_suspended = false;
    candidate.processor_affinity_mask = 0u;

    next_request_id = candidate.request_id + 1u;
    if (next_request_id == 0u) {
        next_request_id = 1u;
    }
    preserved_context = *context;
    (void)vc_apf_record_failure(
        runtime, context, VC_APF_THUNK_EX_CREATE_THREAD,
        VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED);
    runtime->last_failure.related_guest_address = candidate.handle_address;
    runtime->last_failure.owning_guest_thread =
        current_thread->guest_thread_object;
    *context = preserved_context;
    runtime->pending_thread_create = candidate;
    runtime->next_thread_create_request_id = next_request_id;
    current_thread->thread_create_requested = true;
    current_thread->thread_create_request_id = candidate.request_id;
    current_thread->thread_create_context = preserved_context;
    return VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED;
}

static vc_apf_boot_leaf_status vc_apf_rtl_nt_status_to_dos_error(
    vc_apf_guest_ppc_context *context) {
    uint32_t dos_error;

    /*
     * The augmented pre-main frontier reaches this export only at 0x84BF0D64.
     * Its three helper callers pass through a negative NTSTATUS unchanged.
     * The currently resumable upstream adapters prove only these two values.
     * PORTME at 0x84D0864C: extend the table only with licensed, pinned mapping
     * evidence and a proved caller status; never guess ERROR_MR_MID_NOT_FOUND.
     */
    if (context->lr != 0x84BF0D68u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    switch (vc_apf_gpr_u32(context, 3u)) {
    case VC_APF_X_STATUS_INVALID_HANDLE:
        dos_error = VC_APF_X_ERROR_INVALID_HANDLE;
        break;
    case VC_APF_X_STATUS_NO_MEMORY:
        dos_error = VC_APF_X_ERROR_NOT_ENOUGH_MEMORY;
        break;
    default:
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    vc_apf_set_r3(context, dos_error);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_dbg_print(
    vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t format_address = vc_apf_gpr_u32(context, 3u);
    const uint32_t raw_value = vc_apf_gpr_u32(context, 4u);
    uint8_t *format_bytes;
    vc_apf_boot_debug_event event;

    /* Only the one direct retail call and its one-int format may resume. */
    if (context->lr != 0x84BE9EB8u ||
        format_address != VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, format_address,
                           VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_SIZE,
                           &format_bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    if (memcmp(format_bytes, vc_apf_dbg_print_xapi_return_format,
               VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_SIZE) != 0) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }

    memset(&event, 0, sizeof(event));
    event.valid = true;
    event.kind = VC_APF_BOOT_DEBUG_EVENT_XAPI_RETURN_VALUE_S32;
    event.import_thunk = VC_APF_THUNK_DBG_PRINT;
    event.guest_call_address = 0x84BE9EB4u;
    event.guest_return_address = context->lr;
    event.guest_format_address = format_address;
    event.raw_value = raw_value;
    event.signed_decimal_value = (int32_t)raw_value;
    runtime->last_debug_event = event;
    vc_apf_set_r3(context, 0u); /* X_STATUS_SUCCESS. */
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_rtl_image_xex_header_field(
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t header_address = vc_apf_gpr_u32(context, 3u);
    const uint32_t requested_key = vc_apf_gpr_u32(context, 4u);
    uint8_t *header;
    size_t option_index;
    bool requested_key_present = false;

    /* APF reaches exactly this absent-key query at 0x84BF1888. */
    if (context->lr != 0x84BF188Cu ||
        requested_key != VC_APF_XEX_HEADER_DEFAULT_HEAP_SIZE) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (header_address == 0u || (header_address & 3u) != 0u ||
        !vc_apf_guest_span(memory, header_address,
                           VC_APF_RETAIL_XEX_PREFIX_SIZE, &header)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }

    /*
     * Bind the dynamic guest pointer to the SHA-pinned retail header by
     * parsing its complete fixed prefix and all 15 optional-header entries.
     * No header pointer or absent default-heap value is fabricated.
     */
    if (vc_apf_load_be_u32(header) != 0x58455832u || /* XEX2 */
        vc_apf_load_be_u32(header + 4u) != 0x00000001u ||
        vc_apf_load_be_u32(header + 8u) != 0x00007000u ||
        vc_apf_load_be_u32(header + 12u) != 0u ||
        vc_apf_load_be_u32(header + 16u) != 0x00000090u ||
        vc_apf_load_be_u32(header + 20u) !=
            VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }
    for (option_index = 0u;
         option_index < VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT;
         ++option_index) {
        const uint8_t *option = header + 24u + option_index * 8u;
        const uint32_t key = vc_apf_load_be_u32(option);

        if (key != vc_apf_retail_xex_options[option_index].key ||
            vc_apf_load_be_u32(option + 4u) !=
                vc_apf_retail_xex_options[option_index].value_or_offset) {
            return VC_APF_BOOT_LEAF_GUEST_STATE;
        }
        if (key == requested_key) {
            requested_key_present = true;
        }
    }
    if (requested_key_present) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }

    vc_apf_set_r3(context, 0u); /* Header field is absent: return NULL. */
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_rtl_compare_memory_ulong(
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t source = vc_apf_gpr_u32(context, 3u);
    const uint32_t length = vc_apf_gpr_u32(context, 4u);
    const uint32_t pattern = vc_apf_gpr_u32(context, 5u);
    uint8_t *source_bytes;
    uint32_t matched_bytes = 0u;

    if ((source & 3u) != 0u || (length & 3u) != 0u) {
        vc_apf_set_r3(context, 0u);
        return VC_APF_BOOT_LEAF_OK;
    }
    if (length == 0u) {
        vc_apf_set_r3(context, 0u);
        return VC_APF_BOOT_LEAF_OK;
    }
    if (!vc_apf_guest_span(memory, source, length, &source_bytes)) {
        vc_apf_set_r3(context, 0u);
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }

    while (matched_bytes < length) {
        if (vc_apf_load_be_u32(source_bytes + matched_bytes) != pattern) {
            break;
        }
        matched_bytes += 4u;
    }
    vc_apf_set_r3(context, matched_bytes);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_ex_get_xconfig_setting(
    const vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint16_t category = (uint16_t)vc_apf_gpr_u32(context, 3u);
    const uint16_t setting = (uint16_t)vc_apf_gpr_u32(context, 4u);
    const uint32_t buffer_address = vc_apf_gpr_u32(context, 5u);
    const uint16_t buffer_size = (uint16_t)vc_apf_gpr_u32(context, 6u);
    const uint32_t required_size_address = vc_apf_gpr_u32(context, 7u);
    uint32_t value;
    uint8_t *buffer;
    uint8_t *required_size;

    /* PORTME at 0x84D081EC: model additional XConfig variants explicitly. */

    if (category == 2u && setting == 2u) {
        value = runtime->config.secured_av_region;
    } else if (category == 3u && setting == 10u) {
        value = runtime->config.user_video_flags;
    } else {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }

    if (buffer_address == 0u || required_size_address == 0u ||
        buffer_size != 4u || (buffer_address & 3u) != 0u ||
        (required_size_address & 1u) != 0u ||
        vc_apf_spans_overlap(buffer_address, 4u, required_size_address, 2u)) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (!vc_apf_guest_span(memory, buffer_address, 4u, &buffer) ||
        !vc_apf_guest_span(memory, required_size_address, 2u,
                           &required_size)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }

    vc_apf_store_be_u32(buffer, value);
    vc_apf_store_be_u16(required_size, 4u);
    vc_apf_set_r3(context, 0u);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_rtl_init_ansi_string(
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t destination_address = vc_apf_gpr_u32(context, 3u);
    const uint32_t source_address = vc_apf_gpr_u32(context, 4u);
    uint8_t *destination;
    size_t source_length = 0u;
    uint16_t length = 0u;
    uint16_t maximum_length = 0u;

    if (destination_address == 0u || (destination_address & 3u) != 0u ||
        !vc_apf_guest_span(memory, destination_address,
                           VC_APF_ANSI_STRING_SIZE, &destination)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    if (source_address != 0u) {
        if (!vc_apf_guest_c_string_length(memory, source_address,
                                          &source_length)) {
            return VC_APF_BOOT_LEAF_MEMORY_FAULT;
        }
        if (source_length > (size_t)UINT16_MAX - 1u) {
            length = UINT16_MAX - 1u;
            maximum_length = UINT16_MAX;
        } else {
            length = (uint16_t)source_length;
            maximum_length = (uint16_t)(source_length + 1u);
        }
    }

    vc_apf_store_be_u16(destination, length);
    vc_apf_store_be_u16(destination + 2u, maximum_length);
    vc_apf_store_be_u32(destination + 4u, source_address);
    return VC_APF_BOOT_LEAF_OK;
}

static bool vc_apf_span_contains(uint32_t outer_base,
                                 uint32_t outer_size,
                                 uint32_t inner_base,
                                 uint32_t inner_size) {
    return outer_base <= inner_base &&
           (uint64_t)outer_base + outer_size >=
               (uint64_t)inner_base + inner_size;
}

static bool vc_apf_vm_config_valid(
    const vc_apf_boot_leaf_config *config) {
    bool has_title = false;
    bool has_dispatch = false;
    bool has_imports = false;
    size_t range_index;
    uint64_t arena_end;

    if (config->vm_arena_base == 0u ||
        (config->vm_arena_base & (VC_APF_BOOT_VM_PAGE_SIZE - 1u)) != 0u ||
        config->vm_arena_size == 0u ||
        (config->vm_arena_size & (VC_APF_BOOT_VM_PAGE_SIZE - 1u)) != 0u ||
        config->vm_backing_bytes == NULL ||
        config->vm_backing_byte_count != (size_t)config->vm_arena_size ||
        config->vm_arena_size / VC_APF_BOOT_VM_PAGE_SIZE >
            VC_APF_BOOT_VM_MAX_PAGES ||
        config->vm_existing_range_count == 0u ||
        config->vm_existing_range_count >
            VC_APF_BOOT_VM_MAX_EXISTING_RANGES) {
        return false;
    }
    arena_end = (uint64_t)config->vm_arena_base + config->vm_arena_size;
    if (arena_end > (uint64_t)UINT32_MAX + 1u) {
        return false;
    }

    for (range_index = 0u;
         range_index < config->vm_existing_range_count; ++range_index) {
        const vc_apf_boot_vm_existing_range *range =
            &config->vm_existing_ranges[range_index];
        const uint64_t range_end =
            (uint64_t)range->guest_base + range->byte_count;
        bool must_be_separate = false;

        if (range->byte_count == 0u ||
            range_end > (uint64_t)UINT32_MAX + 1u) {
            return false;
        }
        switch (range->kind) {
        case VC_APF_BOOT_VM_RANGE_TITLE_IMAGE:
            has_title = has_title ||
                        vc_apf_span_contains(
                            range->guest_base, range->byte_count,
                            VC_APF_RETAIL_TITLE_BASE,
                            VC_APF_RETAIL_TITLE_SIZE);
            must_be_separate = true;
            break;
        case VC_APF_BOOT_VM_RANGE_STATIC_DISPATCH:
            has_dispatch = has_dispatch ||
                           vc_apf_span_contains(
                               range->guest_base, range->byte_count,
                               VC_APF_STATIC_DISPATCH_BASE,
                               VC_APF_STATIC_DISPATCH_SIZE);
            must_be_separate = true;
            break;
        case VC_APF_BOOT_VM_RANGE_IMPORT_THUNKS:
            has_imports = has_imports ||
                          vc_apf_span_contains(
                              range->guest_base, range->byte_count,
                              VC_APF_RETAIL_IMPORT_THUNK_BASE,
                              VC_APF_RETAIL_IMPORT_THUNK_SPAN);
            must_be_separate = true;
            break;
        case VC_APF_BOOT_VM_RANGE_OTHER_MAPPING:
            break;
        default:
            return false;
        }
        if (must_be_separate &&
            vc_apf_spans_overlap(config->vm_arena_base,
                                 config->vm_arena_size,
                                 range->guest_base,
                                 range->byte_count)) {
            return false;
        }
    }
    return has_title && has_dispatch && has_imports;
}

static void vc_apf_vm_initialize_ledger(vc_apf_boot_leaf_runtime *runtime) {
    size_t range_index;

    runtime->vm_page_count =
        (size_t)(runtime->config.vm_arena_size /
                 VC_APF_BOOT_VM_PAGE_SIZE);
    for (range_index = 0u;
         range_index < runtime->config.vm_existing_range_count;
         ++range_index) {
        const vc_apf_boot_vm_existing_range *range =
            &runtime->config.vm_existing_ranges[range_index];
        uint64_t intersection_start;
        uint64_t intersection_end;
        size_t first_page;
        size_t page_after_last;
        size_t page_index;

        if (range->kind != VC_APF_BOOT_VM_RANGE_OTHER_MAPPING) {
            continue;
        }
        intersection_start = range->guest_base > runtime->config.vm_arena_base
                                 ? range->guest_base
                                 : runtime->config.vm_arena_base;
        intersection_end =
            (uint64_t)range->guest_base + range->byte_count;
        if (intersection_end >
            (uint64_t)runtime->config.vm_arena_base +
                runtime->config.vm_arena_size) {
            intersection_end =
                (uint64_t)runtime->config.vm_arena_base +
                runtime->config.vm_arena_size;
        }
        if (intersection_start >= intersection_end) {
            continue;
        }
        first_page =
            (size_t)((intersection_start - runtime->config.vm_arena_base) /
                     VC_APF_BOOT_VM_PAGE_SIZE);
        page_after_last =
            (size_t)((intersection_end - runtime->config.vm_arena_base +
                      VC_APF_BOOT_VM_PAGE_SIZE - 1u) /
                     VC_APF_BOOT_VM_PAGE_SIZE);
        for (page_index = first_page; page_index < page_after_last;
             ++page_index) {
            runtime->vm_pages[page_index].state = VC_APF_VM_PAGE_EXTERNAL;
        }
    }
}

static bool vc_apf_vm_page_for_address(
    const vc_apf_boot_leaf_runtime *runtime,
    uint32_t address,
    size_t *page_out) {
    uint64_t offset;

    if (address < runtime->config.vm_arena_base) {
        return false;
    }
    offset = (uint64_t)address - runtime->config.vm_arena_base;
    if (offset >= runtime->config.vm_arena_size) {
        return false;
    }
    *page_out = (size_t)(offset / VC_APF_BOOT_VM_PAGE_SIZE);
    return true;
}

static bool vc_apf_vm_round_size(uint32_t requested_size,
                                 uint32_t *rounded_size_out,
                                 size_t *page_count_out) {
    uint64_t rounded_size;

    if (requested_size == 0u || (requested_size & 0x80000000u) != 0u) {
        return false;
    }
    rounded_size =
        ((uint64_t)requested_size + VC_APF_BOOT_VM_PAGE_SIZE - 1u) &
        ~((uint64_t)VC_APF_BOOT_VM_PAGE_SIZE - 1u);
    if (rounded_size == 0u || rounded_size > UINT32_MAX) {
        return false;
    }
    *rounded_size_out = (uint32_t)rounded_size;
    *page_count_out = (size_t)(rounded_size / VC_APF_BOOT_VM_PAGE_SIZE);
    return true;
}

static bool vc_apf_vm_find_free_pages(
    const vc_apf_boot_leaf_runtime *runtime,
    size_t page_count,
    size_t *first_page_out) {
    size_t candidate;

    if (page_count == 0u || page_count > runtime->vm_page_count) {
        return false;
    }
    for (candidate = 0u;
         candidate <= runtime->vm_page_count - page_count; ++candidate) {
        size_t page_index;
        bool all_free = true;
        for (page_index = candidate;
             page_index < candidate + page_count; ++page_index) {
            if (runtime->vm_pages[page_index].state !=
                VC_APF_VM_PAGE_FREE) {
                all_free = false;
                candidate = page_index;
                break;
            }
        }
        if (all_free) {
            *first_page_out = candidate;
            return true;
        }
    }
    return false;
}

static bool vc_apf_vm_find_allocation_slot(
    const vc_apf_boot_leaf_runtime *runtime,
    size_t *slot_out) {
    size_t slot;

    for (slot = 0u; slot < VC_APF_BOOT_VM_MAX_ALLOCATIONS; ++slot) {
        if (!runtime->vm_allocations[slot].active) {
            *slot_out = slot;
            return true;
        }
    }
    return false;
}

static uint32_t vc_apf_vm_allocate(
    vc_apf_boot_leaf_runtime *runtime,
    uint32_t requested_base,
    uint32_t requested_size,
    uint32_t allocation_type,
    uint32_t protect,
    uint32_t *adjusted_base_out,
    uint32_t *adjusted_size_out) {
    const bool reserve =
        (allocation_type & VC_APF_X_MEM_RESERVE) != 0u;
    const bool commit =
        (allocation_type & VC_APF_X_MEM_COMMIT) != 0u;
    const bool nozero =
        (allocation_type & VC_APF_X_MEM_NOZERO) != 0u;
    uint32_t adjusted_size;
    size_t page_count;
    size_t first_page;
    size_t allocation_slot = 0u;
    uint16_t allocation_id = 0u;
    bool new_allocation = false;
    bool was_committed = false;
    size_t page_index;

    if (!vc_apf_vm_round_size(requested_size, &adjusted_size,
                              &page_count)) {
        return VC_APF_X_STATUS_INVALID_PARAMETER;
    }

    if (requested_base == 0u) {
        if (!vc_apf_vm_find_free_pages(runtime, page_count, &first_page)) {
            return VC_APF_X_STATUS_NO_MEMORY;
        }
        new_allocation = true;
    } else {
        const uint32_t adjusted_base =
            requested_base & ~(VC_APF_BOOT_VM_PAGE_SIZE - 1u);
        size_t candidate_page;

        if (!vc_apf_vm_page_for_address(runtime, adjusted_base,
                                        &candidate_page) ||
            page_count > runtime->vm_page_count - candidate_page) {
            return VC_APF_X_STATUS_NO_MEMORY;
        }
        first_page = candidate_page;
        if (reserve) {
            for (page_index = first_page;
                 page_index < first_page + page_count; ++page_index) {
                if (runtime->vm_pages[page_index].state !=
                    VC_APF_VM_PAGE_FREE) {
                    return VC_APF_X_STATUS_NO_MEMORY;
                }
            }
            new_allocation = true;
        } else {
            const vc_apf_boot_vm_page *first =
                &runtime->vm_pages[first_page];
            if (first->state == VC_APF_VM_PAGE_FREE) {
                for (page_index = first_page;
                     page_index < first_page + page_count; ++page_index) {
                    if (runtime->vm_pages[page_index].state !=
                        VC_APF_VM_PAGE_FREE) {
                        return VC_APF_X_STATUS_NO_MEMORY;
                    }
                }
                new_allocation = true;
            } else if (first->state == VC_APF_VM_PAGE_EXTERNAL ||
                       first->allocation_id == 0u) {
                return VC_APF_X_STATUS_NO_MEMORY;
            } else {
                allocation_id = first->allocation_id;
                allocation_slot = (size_t)allocation_id - 1u;
                if (allocation_slot >= VC_APF_BOOT_VM_MAX_ALLOCATIONS ||
                    !runtime->vm_allocations[allocation_slot].active) {
                    return VC_APF_X_STATUS_UNSUCCESSFUL;
                }
                for (page_index = first_page;
                     page_index < first_page + page_count; ++page_index) {
                    const vc_apf_boot_vm_page *page =
                        &runtime->vm_pages[page_index];
                    if (page->allocation_id != allocation_id ||
                        (page->state != VC_APF_VM_PAGE_RESERVE &&
                         page->state != VC_APF_VM_PAGE_COMMIT)) {
                        return VC_APF_X_STATUS_NO_MEMORY;
                    }
                }
            }
        }
    }

    if (new_allocation) {
        if (!vc_apf_vm_find_allocation_slot(runtime, &allocation_slot)) {
            return VC_APF_X_STATUS_NO_MEMORY;
        }
        allocation_id = (uint16_t)(allocation_slot + 1u);
    }

    if (new_allocation) {
        vc_apf_boot_vm_allocation *allocation =
            &runtime->vm_allocations[allocation_slot];
        allocation->base_page = (uint32_t)first_page;
        allocation->page_count = (uint32_t)page_count;
        allocation->allocation_protect = protect;
        allocation->active = true;
        ++runtime->vm_allocation_count;
    }
    was_committed = !new_allocation &&
                    runtime->vm_pages[first_page].state ==
                        VC_APF_VM_PAGE_COMMIT;
    if (commit && !nozero && !was_committed) {
        memset(runtime->config.vm_backing_bytes +
                   first_page * (size_t)VC_APF_BOOT_VM_PAGE_SIZE,
               0, page_count * (size_t)VC_APF_BOOT_VM_PAGE_SIZE);
    }
    for (page_index = first_page; page_index < first_page + page_count;
         ++page_index) {
        vc_apf_boot_vm_page *page = &runtime->vm_pages[page_index];
        page->allocation_id = allocation_id;
        page->state = commit ? VC_APF_VM_PAGE_COMMIT
                             : VC_APF_VM_PAGE_RESERVE;
        page->protect = (uint8_t)protect;
    }

    *adjusted_base_out =
        runtime->config.vm_arena_base +
        (uint32_t)(first_page * (size_t)VC_APF_BOOT_VM_PAGE_SIZE);
    *adjusted_size_out = adjusted_size;
    return VC_APF_X_STATUS_SUCCESS;
}

static uint32_t vc_apf_vm_free(vc_apf_boot_leaf_runtime *runtime,
                               uint32_t base_address,
                               uint32_t region_size,
                               uint32_t free_type,
                               uint32_t *base_out,
                               uint32_t *size_out) {
    size_t first_page;
    const vc_apf_boot_vm_page *first;
    size_t allocation_slot;
    vc_apf_boot_vm_allocation *allocation;
    uint16_t allocation_id;
    size_t page_index;

    if (base_address == 0u) {
        return VC_APF_X_STATUS_MEMORY_NOT_ALLOCATED;
    }
    if (!vc_apf_vm_page_for_address(runtime, base_address, &first_page)) {
        return VC_APF_X_STATUS_INVALID_PARAMETER;
    }
    first = &runtime->vm_pages[first_page];
    if (first->state == VC_APF_VM_PAGE_FREE ||
        first->state == VC_APF_VM_PAGE_EXTERNAL ||
        first->allocation_id == 0u) {
        return VC_APF_X_STATUS_UNSUCCESSFUL;
    }
    allocation_id = first->allocation_id;
    allocation_slot = (size_t)allocation_id - 1u;
    if (allocation_slot >= VC_APF_BOOT_VM_MAX_ALLOCATIONS ||
        !runtime->vm_allocations[allocation_slot].active) {
        return VC_APF_X_STATUS_UNSUCCESSFUL;
    }
    allocation = &runtime->vm_allocations[allocation_slot];

    if (free_type == VC_APF_X_MEM_DECOMMIT) {
        uint32_t rounded_size;
        size_t page_count;

        if (!vc_apf_vm_round_size(region_size, &rounded_size,
                                  &page_count) ||
            page_count > runtime->vm_page_count - first_page) {
            return VC_APF_X_STATUS_UNSUCCESSFUL;
        }
        for (page_index = first_page;
             page_index < first_page + page_count; ++page_index) {
            const vc_apf_boot_vm_page *page =
                &runtime->vm_pages[page_index];
            if (page->allocation_id != allocation_id ||
                (page->state != VC_APF_VM_PAGE_RESERVE &&
                 page->state != VC_APF_VM_PAGE_COMMIT)) {
                return VC_APF_X_STATUS_UNSUCCESSFUL;
            }
        }
        for (page_index = first_page;
             page_index < first_page + page_count; ++page_index) {
            runtime->vm_pages[page_index].state =
                VC_APF_VM_PAGE_RESERVE;
        }
        *base_out = base_address;
        *size_out = rounded_size;
        return VC_APF_X_STATUS_SUCCESS;
    }

    if (first_page != (size_t)allocation->base_page) {
        return VC_APF_X_STATUS_UNSUCCESSFUL;
    }
    for (page_index = allocation->base_page;
         page_index < (size_t)allocation->base_page + allocation->page_count;
         ++page_index) {
        memset(&runtime->vm_pages[page_index], 0,
               sizeof(runtime->vm_pages[page_index]));
    }
    *base_out = base_address;
    *size_out = allocation->page_count * VC_APF_BOOT_VM_PAGE_SIZE;
    memset(allocation, 0, sizeof(*allocation));
    --runtime->vm_allocation_count;
    return VC_APF_X_STATUS_SUCCESS;
}

static uint32_t vc_apf_vm_query(
    const vc_apf_boot_leaf_runtime *runtime,
    uint32_t base_address,
    uint32_t values_out[7]) {
    size_t first_page;
    const vc_apf_boot_vm_page *first;
    size_t page_after_last;

    if (!vc_apf_vm_page_for_address(runtime, base_address, &first_page)) {
        return VC_APF_X_STATUS_INVALID_PARAMETER;
    }
    first = &runtime->vm_pages[first_page];
    if (first->state == VC_APF_VM_PAGE_EXTERNAL) {
        return VC_APF_X_STATUS_INVALID_PARAMETER;
    }

    values_out[0] = base_address;
    values_out[1] = 0u;
    values_out[2] = 0u;
    values_out[4] = VC_APF_X_MEM_FREE;
    values_out[5] = 0u;
    values_out[6] = VC_APF_X_MEM_PRIVATE;
    page_after_last = first_page;

    if (first->state == VC_APF_VM_PAGE_FREE) {
        while (page_after_last < runtime->vm_page_count &&
               runtime->vm_pages[page_after_last].state ==
                   VC_APF_VM_PAGE_FREE) {
            ++page_after_last;
        }
    } else {
        const size_t allocation_slot =
            (size_t)first->allocation_id - 1u;
        const vc_apf_boot_vm_allocation *allocation;

        if (first->allocation_id == 0u ||
            allocation_slot >= VC_APF_BOOT_VM_MAX_ALLOCATIONS ||
            !runtime->vm_allocations[allocation_slot].active) {
            return VC_APF_X_STATUS_UNSUCCESSFUL;
        }
        allocation = &runtime->vm_allocations[allocation_slot];
        values_out[1] =
            runtime->config.vm_arena_base +
            allocation->base_page * VC_APF_BOOT_VM_PAGE_SIZE;
        values_out[2] = allocation->allocation_protect;
        values_out[4] = first->state == VC_APF_VM_PAGE_COMMIT
                            ? VC_APF_X_MEM_COMMIT
                            : VC_APF_X_MEM_RESERVE;
        values_out[5] = first->protect;
        while (page_after_last < runtime->vm_page_count) {
            const vc_apf_boot_vm_page *page =
                &runtime->vm_pages[page_after_last];
            if (page->allocation_id != first->allocation_id ||
                page->state != first->state ||
                page->protect != first->protect) {
                break;
            }
            ++page_after_last;
        }
    }
    values_out[3] =
        (uint32_t)((page_after_last - first_page) *
                   (size_t)VC_APF_BOOT_VM_PAGE_SIZE);
    return VC_APF_X_STATUS_SUCCESS;
}

static bool vc_apf_vm_allocate_site_type(uint32_t return_address,
                                         bool *reserve_out,
                                         bool *nozero_allowed_out) {
    *reserve_out = false;
    *nozero_allowed_out = false;
    switch (return_address) {
    case 0x84BEBB20u:
    case 0x84BED010u:
    case 0x84BED054u:
    case 0x84BED7BCu:
        *reserve_out = true;
        return true;
    case 0x84BEE1D0u:
        *nozero_allowed_out = true;
        return true;
    case 0x84BEBAD0u:
    case 0x84BEBB54u:
    case 0x84BEBE10u:
    case 0x84BECE18u:
    case 0x84BED0A4u:
    case 0x84BED80Cu:
        return true;
    default:
        return false;
    }
}

static vc_apf_boot_leaf_status vc_apf_nt_allocate_virtual_memory(
    vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t base_pointer = vc_apf_gpr_u32(context, 3u);
    const uint32_t size_pointer = vc_apf_gpr_u32(context, 4u);
    const uint32_t allocation_type = vc_apf_gpr_u32(context, 5u);
    const uint32_t protect = vc_apf_gpr_u32(context, 6u);
    const uint32_t debug_memory = vc_apf_gpr_u32(context, 7u);
    const uint32_t common_flags =
        VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP;
    bool reserve_site;
    bool nozero_allowed;
    uint8_t *base_bytes;
    uint8_t *size_bytes;
    uint32_t requested_base;
    uint32_t requested_size;
    uint32_t adjusted_base = 0u;
    uint32_t adjusted_size = 0u;
    uint32_t guest_status;
    uint32_t expected_type;

    /* PORTME at 0x84D0863C: recover non-frontier VM flags and protections. */

    if (!vc_apf_vm_allocate_site_type(context->lr, &reserve_site,
                                      &nozero_allowed)) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    expected_type = common_flags |
                    (reserve_site ? VC_APF_X_MEM_RESERVE
                                  : VC_APF_X_MEM_COMMIT);
    if ((allocation_type != expected_type &&
         !(nozero_allowed &&
           allocation_type == (expected_type | VC_APF_X_MEM_NOZERO))) ||
        protect != VC_APF_X_PAGE_READWRITE || debug_memory != 0u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (base_pointer == 0u || size_pointer == 0u ||
        (base_pointer & 3u) != 0u || (size_pointer & 3u) != 0u ||
        vc_apf_spans_overlap(base_pointer, 4u, size_pointer, 4u) ||
        !vc_apf_guest_span(memory, base_pointer, 4u, &base_bytes) ||
        !vc_apf_guest_span(memory, size_pointer, 4u, &size_bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    requested_base = vc_apf_load_be_u32(base_bytes);
    requested_size = vc_apf_load_be_u32(size_bytes);
    guest_status = vc_apf_vm_allocate(
        runtime, requested_base, requested_size, allocation_type, protect,
        &adjusted_base, &adjusted_size);
    if (guest_status == VC_APF_X_STATUS_SUCCESS) {
        vc_apf_store_be_u32(base_bytes, adjusted_base);
        vc_apf_store_be_u32(size_bytes, adjusted_size);
    }
    vc_apf_set_r3(context, guest_status);
    return VC_APF_BOOT_LEAF_OK;
}

static bool vc_apf_vm_free_site_type(uint32_t return_address,
                                     uint32_t *free_type_out) {
    switch (return_address) {
    case 0x84BED248u:
        *free_type_out = VC_APF_X_MEM_DECOMMIT;
        return true;
    case 0x84BEBB74u:
    case 0x84BED110u:
    case 0x84BED834u:
    case 0x84BEEF40u:
    case 0x84BEF510u:
        *free_type_out = VC_APF_X_MEM_RELEASE;
        return true;
    default:
        return false;
    }
}

static vc_apf_boot_leaf_status vc_apf_nt_free_virtual_memory(
    vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t base_pointer = vc_apf_gpr_u32(context, 3u);
    const uint32_t size_pointer = vc_apf_gpr_u32(context, 4u);
    const uint32_t free_type = vc_apf_gpr_u32(context, 5u);
    const uint32_t debug_memory = vc_apf_gpr_u32(context, 6u);
    uint32_t expected_free_type;
    uint8_t *base_bytes;
    uint8_t *size_bytes;
    uint32_t base_address;
    uint32_t region_size;
    uint32_t result_base = 0u;
    uint32_t result_size = 0u;
    uint32_t guest_status;

    /* PORTME at 0x84D085EC: recover non-frontier free types and heap paths. */

    if (!vc_apf_vm_free_site_type(context->lr, &expected_free_type) ||
        free_type != expected_free_type || debug_memory != 0u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (base_pointer == 0u || size_pointer == 0u ||
        (base_pointer & 3u) != 0u || (size_pointer & 3u) != 0u ||
        vc_apf_spans_overlap(base_pointer, 4u, size_pointer, 4u) ||
        !vc_apf_guest_span(memory, base_pointer, 4u, &base_bytes) ||
        !vc_apf_guest_span(memory, size_pointer, 4u, &size_bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    base_address = vc_apf_load_be_u32(base_bytes);
    region_size = vc_apf_load_be_u32(size_bytes);
    guest_status = vc_apf_vm_free(runtime, base_address, region_size,
                                  free_type, &result_base, &result_size);
    if (guest_status == VC_APF_X_STATUS_SUCCESS) {
        vc_apf_store_be_u32(base_bytes, result_base);
        vc_apf_store_be_u32(size_bytes, result_size);
    }
    vc_apf_set_r3(context, guest_status);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_nt_query_virtual_memory(
    const vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context) {
    const uint32_t base_address = vc_apf_gpr_u32(context, 3u);
    const uint32_t information_pointer = vc_apf_gpr_u32(context, 4u);
    uint8_t *information;
    uint32_t values[7];
    uint32_t guest_status;
    size_t value_index;

    /* PORTME at 0x84D086BC: query other guest heaps only with loader maps. */

    if ((context->lr != 0x84BED6FCu && context->lr != 0x84BED754u) ||
        vc_apf_gpr_u32(context, 5u) != 0u) {
        return VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT;
    }
    if (information_pointer == 0u || (information_pointer & 3u) != 0u ||
        !vc_apf_guest_span(memory, information_pointer,
                           VC_APF_MEMORY_BASIC_INFORMATION_SIZE,
                           &information)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    guest_status = vc_apf_vm_query(runtime, base_address, values);
    if (guest_status == VC_APF_X_STATUS_SUCCESS) {
        for (value_index = 0u; value_index < 7u; ++value_index) {
            vc_apf_store_be_u32(information + value_index * 4u,
                                values[value_index]);
        }
    }
    vc_apf_set_r3(context, guest_status);
    return VC_APF_BOOT_LEAF_OK;
}

typedef struct vc_apf_critical_section_view {
    uint8_t *bytes;
    int32_t lock_count;
    uint32_t recursion_count;
    uint32_t owning_thread;
    bool wait_list_empty;
} vc_apf_critical_section_view;

static vc_apf_boot_leaf_status vc_apf_load_critical_section(
    const vc_apf_guest_memory *memory,
    uint32_t address,
    vc_apf_critical_section_view *view) {
    const uint32_t wait_list_head = address + 8u;
    uint32_t wait_list_flink;
    uint32_t wait_list_blink;

    if (address == 0u || (address & 3u) != 0u ||
        !vc_apf_guest_span(memory, address, VC_APF_RTL_CRITICAL_SECTION_SIZE,
                           &view->bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }
    view->lock_count = vc_apf_load_be_s32(view->bytes + 16u);
    view->recursion_count = vc_apf_load_be_u32(view->bytes + 20u);
    view->owning_thread = vc_apf_load_be_u32(view->bytes + 24u);
    wait_list_flink = vc_apf_load_be_u32(view->bytes + 8u);
    wait_list_blink = vc_apf_load_be_u32(view->bytes + 12u);
    view->wait_list_empty = wait_list_flink == wait_list_head &&
                            wait_list_blink == wait_list_head;

    if (view->bytes[0] != 1u || view->bytes[2] != 4u ||
        view->bytes[3] != 0u || vc_apf_load_be_u32(view->bytes + 4u) != 0u ||
        ((wait_list_flink == wait_list_head) !=
         (wait_list_blink == wait_list_head)) ||
        (!view->wait_list_empty &&
         (wait_list_flink == 0u || wait_list_blink == 0u))) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }
    if (view->owning_thread == 0u) {
        if (view->lock_count != -1 || view->recursion_count != 0u ||
            !view->wait_list_empty) {
            return VC_APF_BOOT_LEAF_GUEST_STATE;
        }
    } else if (view->recursion_count == 0u ||
               view->recursion_count > (uint32_t)INT32_MAX ||
               view->lock_count <
                   (int32_t)(view->recursion_count - 1u)) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }
    if (view->owning_thread != 0u &&
        view->lock_count == (int32_t)(view->recursion_count - 1u) &&
        !view->wait_list_empty) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_rtl_initialize_critical_section(
    const vc_apf_guest_memory *memory,
    uint32_t address) {
    uint8_t *bytes;

    if (address == 0u || (address & 3u) != 0u ||
        !vc_apf_guest_span(memory, address, VC_APF_RTL_CRITICAL_SECTION_SIZE,
                           &bytes)) {
        return VC_APF_BOOT_LEAF_MEMORY_FAULT;
    }

    memset(bytes, 0, VC_APF_RTL_CRITICAL_SECTION_SIZE);
    bytes[0] = 1u; /* SynchronizationEvent. */
    bytes[2] = 4u; /* sizeof(X_DISPATCH_HEADER) / sizeof(uint32_t). */
    vc_apf_store_be_u32(bytes + 8u, address + 8u);
    vc_apf_store_be_u32(bytes + 12u, address + 8u);
    vc_apf_store_be_u32(bytes + 16u, UINT32_MAX);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_rtl_enter_critical_section(
    const vc_apf_guest_memory *memory,
    uint32_t address,
    uint32_t current_thread,
    uint32_t *owner_out) {
    vc_apf_critical_section_view view;
    vc_apf_boot_leaf_status status =
        vc_apf_load_critical_section(memory, address, &view);

    /* PORTME at 0x84D07FCC: park/wake a contending guest thread. */

    if (status != VC_APF_BOOT_LEAF_OK) {
        return status;
    }
    *owner_out = view.owning_thread;
    if (view.owning_thread == 0u) {
        vc_apf_store_be_u32(view.bytes + 16u, 0u);
        vc_apf_store_be_u32(view.bytes + 20u, 1u);
        vc_apf_store_be_u32(view.bytes + 24u, current_thread);
        return VC_APF_BOOT_LEAF_OK;
    }
    if (view.owning_thread != current_thread) {
        return VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED;
    }
    if (view.lock_count != (int32_t)(view.recursion_count - 1u)) {
        return VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED;
    }
    if (view.lock_count == INT32_MAX ||
        view.recursion_count == (uint32_t)INT32_MAX) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }

    vc_apf_store_be_u32(view.bytes + 16u,
                        (uint32_t)(view.lock_count + 1));
    vc_apf_store_be_u32(view.bytes + 20u, view.recursion_count + 1u);
    return VC_APF_BOOT_LEAF_OK;
}

static vc_apf_boot_leaf_status vc_apf_rtl_leave_critical_section(
    const vc_apf_guest_memory *memory,
    uint32_t address,
    uint32_t current_thread,
    uint32_t *owner_out) {
    vc_apf_critical_section_view view;
    vc_apf_boot_leaf_status status =
        vc_apf_load_critical_section(memory, address, &view);

    /* PORTME at 0x84D07FDC: release and wake one queued guest waiter. */

    if (status != VC_APF_BOOT_LEAF_OK) {
        return status;
    }
    *owner_out = view.owning_thread;
    if (view.owning_thread == 0u || view.owning_thread != current_thread) {
        return VC_APF_BOOT_LEAF_GUEST_STATE;
    }
    if (view.lock_count != (int32_t)(view.recursion_count - 1u)) {
        return VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED;
    }
    if (view.recursion_count > 1u) {
        vc_apf_store_be_u32(view.bytes + 16u,
                            (uint32_t)(view.lock_count - 1));
        vc_apf_store_be_u32(view.bytes + 20u, view.recursion_count - 1u);
    } else {
        vc_apf_store_be_u32(view.bytes + 16u, UINT32_MAX);
        vc_apf_store_be_u32(view.bytes + 20u, 0u);
        vc_apf_store_be_u32(view.bytes + 24u, 0u);
    }
    return VC_APF_BOOT_LEAF_OK;
}

vc_apf_boot_leaf_status vc_apf_boot_leaf_runtime_init(
    vc_apf_boot_leaf_runtime *runtime,
    const vc_apf_boot_leaf_config *config) {
    if (runtime == NULL || config == NULL ||
        config->configured_fields != VC_APF_BOOT_CONFIG_ALL ||
        config->process_type > 2u || config->language == 0u ||
        config->language >= 13u || !vc_apf_vm_config_valid(config)) {
        return VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
    }

    memset(runtime, 0, sizeof(*runtime));
    runtime->config = *config;
    runtime->initialized_cookie = VC_APF_BOOT_LEAF_COOKIE;
    runtime->next_ui_request_id = 1u;
    runtime->next_thread_create_request_id = 1u;
    vc_apf_clear_runtime_thread_create_request(runtime);
    vc_apf_vm_initialize_ledger(runtime);
    vc_apf_clear_failure(runtime);
    return VC_APF_BOOT_LEAF_OK;
}

void vc_apf_boot_leaf_thread_init(vc_apf_guest_thread *thread) {
    if (thread != NULL) {
        memset(thread, 0, sizeof(*thread));
        thread->initialized_cookie = VC_APF_BOOT_THREAD_COOKIE;
    }
}

vc_apf_boot_leaf_status vc_apf_boot_leaf_thread_attach(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    uint32_t guest_thread_object) {
    size_t index;

    if (!vc_apf_runtime_ready(runtime) || thread == NULL) {
        return VC_APF_BOOT_LEAF_CONFIG_REQUIRED;
    }
    for (index = 0u; index < runtime->thread_count; ++index) {
        if (runtime->threads[index] == thread ||
            runtime->threads[index]->guest_thread_object ==
                guest_thread_object) {
            return VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
        }
    }
    if (thread->initialized_cookie != VC_APF_BOOT_THREAD_COOKIE ||
        thread->owner != NULL || guest_thread_object == 0u ||
        (guest_thread_object & 3u) != 0u) {
        return VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
    }
    if (runtime->thread_count >= VC_APF_BOOT_MAX_GUEST_THREADS) {
        return VC_APF_BOOT_LEAF_THREAD_CAPACITY;
    }

    thread->owner = runtime;
    thread->guest_thread_object = guest_thread_object;
    runtime->threads[runtime->thread_count++] = thread;
    return VC_APF_BOOT_LEAF_OK;
}

vc_apf_boot_leaf_status vc_apf_boot_leaf_thread_detach(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread) {
    size_t index;

    if (!vc_apf_runtime_ready(runtime) || thread == NULL ||
        thread->owner != runtime) {
        return VC_APF_BOOT_LEAF_THREAD_REQUIRED;
    }
    if (thread->exception_required) {
        return VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED;
    }
    if (thread->ui_requested) {
        return VC_APF_BOOT_LEAF_UI_REQUESTED;
    }
    if (thread->thread_create_requested) {
        return VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED;
    }
    if (thread->scheduler_blocked) {
        return VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED;
    }
    for (index = 0u; index < runtime->thread_count; ++index) {
        if (runtime->threads[index] == thread) {
            size_t move_index;
            for (move_index = index + 1u; move_index < runtime->thread_count;
                 ++move_index) {
                runtime->threads[move_index - 1u] =
                    runtime->threads[move_index];
            }
            --runtime->thread_count;
            runtime->threads[runtime->thread_count] = NULL;
            memset(thread->tls_values, 0, sizeof(thread->tls_values));
            thread->owner = NULL;
            thread->guest_thread_object = 0u;
            vc_apf_clear_scheduler_block(thread);
            vc_apf_clear_thread_ui_request(thread);
            vc_apf_clear_thread_create_request(thread);
            return VC_APF_BOOT_LEAF_OK;
        }
    }
    return VC_APF_BOOT_LEAF_THREAD_REQUIRED;
}

vc_apf_boot_leaf_status vc_apf_boot_leaf_dispatch(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *current_thread,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk) {
    vc_apf_boot_leaf_status status;

    if (!vc_apf_runtime_ready(runtime)) {
        return vc_apf_record_failure(runtime, context, import_thunk,
                                     VC_APF_BOOT_LEAF_CONFIG_REQUIRED);
    }
    if (context == NULL) {
        return vc_apf_record_failure(runtime, NULL, import_thunk,
                                     VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    }
    if (!vc_apf_current_thread_ready(runtime, current_thread)) {
        return vc_apf_record_failure(runtime, context, import_thunk,
                                     VC_APF_BOOT_LEAF_THREAD_REQUIRED);
    }
    if (current_thread->exception_required) {
        const vc_apf_guest_ppc_context preserved_context =
            current_thread->exception_context;

        *context = preserved_context;
        (void)vc_apf_record_failure(runtime, context,
                                    current_thread->exception_import_thunk,
                                    VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED);
        *context = preserved_context;
        return VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED;
    }
    if (current_thread->ui_requested) {
        const vc_apf_guest_ppc_context preserved_context =
            current_thread->ui_context;
        const uint32_t overlapped_address =
            runtime->pending_message_box.overlapped_address;

        *context = preserved_context;
        (void)vc_apf_record_failure(
            runtime, context, VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX,
            VC_APF_BOOT_LEAF_UI_REQUESTED);
        runtime->last_failure.related_guest_address = overlapped_address;
        runtime->last_failure.owning_guest_thread =
            current_thread->guest_thread_object;
        *context = preserved_context;
        return VC_APF_BOOT_LEAF_UI_REQUESTED;
    }
    if (current_thread->thread_create_requested) {
        const vc_apf_guest_ppc_context preserved_context =
            current_thread->thread_create_context;
        const uint32_t handle_address =
            runtime->pending_thread_create.handle_address;

        *context = preserved_context;
        (void)vc_apf_record_failure(
            runtime, context, VC_APF_THUNK_EX_CREATE_THREAD,
            VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED);
        runtime->last_failure.related_guest_address = handle_address;
        runtime->last_failure.owning_guest_thread =
            current_thread->guest_thread_object;
        *context = preserved_context;
        return VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED;
    }
    if (current_thread->scheduler_blocked) {
        if (import_thunk != current_thread->blocked_import_thunk ||
            vc_apf_gpr_u32(context, 3u) !=
                current_thread->blocked_guest_address ||
            context->lr != current_thread->blocked_return_address) {
            const uint32_t blocked_address =
                current_thread->blocked_guest_address;
            const uint32_t blocked_owner =
                current_thread->blocked_owner_guest_thread;
            (void)vc_apf_record_failure(runtime, context, import_thunk,
                                        VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED);
            runtime->last_failure.related_guest_address = blocked_address;
            runtime->last_failure.owning_guest_thread = blocked_owner;
            vc_apf_set_r3(context, blocked_address);
            return VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED;
        }
        vc_apf_clear_scheduler_block(current_thread);
    }

    vc_apf_clear_failure(runtime);
    switch (import_thunk) {
    case VC_APF_THUNK_RTL_INIT_ANSI_STRING:
        status = vc_apf_rtl_init_ansi_string(memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_EX_GET_XCONFIG_SETTING:
        status = vc_apf_ex_get_xconfig_setting(runtime, memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION: {
        const uint32_t critical_section = vc_apf_gpr_u32(context, 3u);
        status = vc_apf_rtl_initialize_critical_section(memory,
                                                        critical_section);
        if (status != VC_APF_BOOT_LEAF_OK) {
            (void)vc_apf_record_failure(runtime, context, import_thunk,
                                        status);
            runtime->last_failure.related_guest_address = critical_section;
            return status;
        }
        return status;
    }
    case VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION: {
        const uint32_t critical_section = vc_apf_gpr_u32(context, 3u);
        uint32_t owner = 0u;
        status = vc_apf_rtl_enter_critical_section(
            memory, critical_section, current_thread->guest_thread_object,
            &owner);
        if (status != VC_APF_BOOT_LEAF_OK) {
            if (status == VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED) {
                return vc_apf_record_scheduler_block(
                    runtime, current_thread, context, import_thunk,
                    critical_section, owner);
            }
            (void)vc_apf_record_failure(runtime, context, import_thunk,
                                        status);
            runtime->last_failure.related_guest_address = critical_section;
            runtime->last_failure.owning_guest_thread = owner;
            return status;
        }
        return status;
    }
    case VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION: {
        const uint32_t critical_section = vc_apf_gpr_u32(context, 3u);
        uint32_t owner = 0u;
        status = vc_apf_rtl_leave_critical_section(
            memory, critical_section, current_thread->guest_thread_object,
            &owner);
        if (status != VC_APF_BOOT_LEAF_OK) {
            if (status == VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED) {
                return vc_apf_record_scheduler_block(
                    runtime, current_thread, context, import_thunk,
                    critical_section, owner);
            }
            (void)vc_apf_record_failure(runtime, context, import_thunk,
                                        status);
            runtime->last_failure.related_guest_address = critical_section;
            runtime->last_failure.owning_guest_thread = owner;
            return status;
        }
        return status;
    }
    case VC_APF_THUNK_KE_TLS_ALLOC:
        return vc_apf_ke_tls_alloc(runtime, current_thread, context);
    case VC_APF_THUNK_KE_TLS_FREE:
        return vc_apf_ke_tls_free(runtime, context);
    case VC_APF_THUNK_KE_TLS_GET_VALUE:
        return vc_apf_ke_tls_get_value(runtime, current_thread, context);
    case VC_APF_THUNK_KE_TLS_SET_VALUE:
        return vc_apf_ke_tls_set_value(runtime, current_thread, context);
    case VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE:
        vc_apf_set_r3(context, runtime->config.process_type);
        return VC_APF_BOOT_LEAF_OK;
    case VC_APF_THUNK_XGET_AV_PACK:
        vc_apf_set_r3(context, runtime->config.av_pack);
        return VC_APF_BOOT_LEAF_OK;
    case VC_APF_THUNK_XGET_LANGUAGE:
        vc_apf_set_r3(context, runtime->config.language);
        return VC_APF_BOOT_LEAF_OK;
    case VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE: {
        const uint32_t privilege = vc_apf_gpr_u32(context, 3u);
        const uint32_t present =
            privilege < 32u &&
                    (runtime->config.executable_system_flags &
                     (UINT32_C(1) << privilege)) != 0u
                ? 1u
                : 0u;
        vc_apf_set_r3(context, present);
        return VC_APF_BOOT_LEAF_OK;
    }
    case VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG:
        status = vc_apf_rtl_compare_memory_ulong(memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_DBG_PRINT:
        status = vc_apf_dbg_print(runtime, memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD:
        status = vc_apf_rtl_image_xex_header_field(memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY:
        status = vc_apf_nt_allocate_virtual_memory(runtime, memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY:
        status = vc_apf_nt_free_virtual_memory(runtime, memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY:
        status = vc_apf_nt_query_virtual_memory(runtime, memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_NT_CREATE_EVENT:
        status = vc_apf_nt_create_event(runtime, memory, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_NT_CLOSE:
        status = vc_apf_nt_close(runtime, context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX:
        status = vc_apf_nt_wait_for_single_object_ex(runtime, memory,
                                                     context);
        if (status == VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED) {
            return vc_apf_record_scheduler_block(
                runtime, current_thread, context, import_thunk,
                vc_apf_gpr_u32(context, 3u), 0u);
        }
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR:
        status = vc_apf_rtl_nt_status_to_dos_error(context);
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX:
        status = vc_apf_xam_show_message_box_ui_ex(
            runtime, current_thread, memory, context);
        if (status == VC_APF_BOOT_LEAF_UI_REQUESTED) {
            return status;
        }
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_EX_CREATE_THREAD:
        status = vc_apf_ex_create_thread_request(
            runtime, current_thread, memory, context);
        if (status == VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED) {
            return status;
        }
        if (status != VC_APF_BOOT_LEAF_OK) {
            return vc_apf_record_failure(runtime, context, import_thunk,
                                         status);
        }
        return status;
    case VC_APF_THUNK_HAL_RETURN_TO_FIRMWARE:
        return vc_apf_record_terminal(runtime, context, import_thunk,
                                      VC_APF_BOOT_TERMINAL_FIRMWARE_RETURN);
    case VC_APF_THUNK_KE_BUG_CHECK_EX:
        return vc_apf_record_terminal(runtime, context, import_thunk,
                                      VC_APF_BOOT_TERMINAL_BUGCHECK);
    case VC_APF_THUNK_KE_BUG_CHECK:
        return vc_apf_record_terminal(runtime, context, import_thunk,
                                      VC_APF_BOOT_TERMINAL_BUGCHECK);
    case VC_APF_THUNK_RTL_RAISE_EXCEPTION:
        /* PORTME at 0x84D086CC: integrate guest exception dispatch/unwind. */
        return vc_apf_record_exception_required(runtime, current_thread,
                                                context, import_thunk);
    case VC_APF_THUNK_XAM_LOADER_TERMINATE_TITLE:
        return vc_apf_record_terminal(runtime, context, import_thunk,
                                      VC_APF_BOOT_TERMINAL_TITLE_TERMINATE);

    default:
        return vc_apf_record_failure(runtime, context, import_thunk,
                                     VC_APF_BOOT_LEAF_UNKNOWN_IMPORT);
    }
}

const char *vc_apf_boot_leaf_status_name(vc_apf_boot_leaf_status status) {
    switch (status) {
    case VC_APF_BOOT_LEAF_OK:
        return "ok";
    case VC_APF_BOOT_LEAF_INVALID_ARGUMENT:
        return "invalid_argument";
    case VC_APF_BOOT_LEAF_CONFIG_REQUIRED:
        return "config_required";
    case VC_APF_BOOT_LEAF_THREAD_REQUIRED:
        return "thread_required";
    case VC_APF_BOOT_LEAF_THREAD_CAPACITY:
        return "thread_capacity";
    case VC_APF_BOOT_LEAF_MEMORY_FAULT:
        return "memory_fault";
    case VC_APF_BOOT_LEAF_GUEST_STATE:
        return "guest_state";
    case VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED:
        return "scheduler_blocked";
    case VC_APF_BOOT_LEAF_UI_REQUESTED:
        return "ui_requested";
    case VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED:
        return "thread_create_requested";
    case VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT:
        return "unsupported_variant";
    case VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED:
        return "exception_required";
    case VC_APF_BOOT_LEAF_TERMINAL_OUTCOME:
        return "terminal_outcome";
    case VC_APF_BOOT_LEAF_UNSUPPORTED_IMPORT:
        return "unsupported_import";
    case VC_APF_BOOT_LEAF_UNKNOWN_IMPORT:
        return "unknown_import";
    default:
        return "invalid_status";
    }
}
