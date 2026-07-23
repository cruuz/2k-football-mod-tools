#define _GNU_SOURCE

#include "static_runtime/apf_first_entry_gate.h"

#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static const vc_apf_first_entry_import_binding vc_apf_frontier_bindings[] = {
    {VC_APF_THUNK_XGET_LANGUAGE, "XGetLanguage",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_XGET_AV_PACK, "XGetAVPack",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION,
     "RtlInitializeCriticalSection", VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, "RtlEnterCriticalSection",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, "RtlLeaveCriticalSection",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_XAM_LOADER_TERMINATE_TITLE, "XamLoaderTerminateTitle",
     VC_APF_FIRST_ENTRY_IMPORT_TERMINAL},
    {VC_APF_THUNK_RTL_INIT_ANSI_STRING, "RtlInitAnsiString",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_KE_BUG_CHECK, "KeBugCheck",
     VC_APF_FIRST_ENTRY_IMPORT_TERMINAL},
    {VC_APF_THUNK_NT_CREATE_EVENT, "NtCreateEvent",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_NT_CLOSE, "NtClose",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_EX_GET_XCONFIG_SETTING, "ExGetXConfigSetting",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_DBG_PRINT, "DbgPrint",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_KE_TLS_ALLOC, "KeTlsAlloc",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_KE_TLS_GET_VALUE, "KeTlsGetValue",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_KE_TLS_SET_VALUE, "KeTlsSetValue",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_KE_TLS_FREE, "KeTlsFree",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE,
     "XexCheckExecutablePrivilege", VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_KE_BUG_CHECK_EX, "KeBugCheckEx",
     VC_APF_FIRST_ENTRY_IMPORT_TERMINAL},
    {VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE, "KeGetCurrentProcessType",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG, "RtlCompareMemoryUlong",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_RTL_RAISE_EXCEPTION, "RtlRaiseException",
     VC_APF_FIRST_ENTRY_IMPORT_EXCEPTION_REQUIRED},
    {VC_APF_THUNK_EX_CREATE_THREAD, "ExCreateThread",
     VC_APF_FIRST_ENTRY_IMPORT_THREAD_CREATE_REQUIRED},
    {VC_APF_THUNK_HAL_RETURN_TO_FIRMWARE, "HalReturnToFirmware",
     VC_APF_FIRST_ENTRY_IMPORT_TERMINAL},
    {VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD, "RtlImageXexHeaderField",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY, "NtAllocateVirtualMemory",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY, "NtFreeVirtualMemory",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY, "NtQueryVirtualMemory",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX, "NtWaitForSingleObjectEx",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR, "RtlNtStatusToDosError",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
    {VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX, "XamShowMessageBoxUIEx",
     VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE},
};

_Static_assert(sizeof(vc_apf_frontier_bindings) /
                       sizeof(vc_apf_frontier_bindings[0]) ==
                   VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT,
               "APF first-entry binding count changed");
_Static_assert(VC_APF_FIRST_ENTRY_STACK_TOP % 16u == 0u,
               "APF loader stack must satisfy the Xenon ABI alignment");
_Static_assert(VC_APF_FIRST_ENTRY_LOADER_ARENA_SIZE >=
                   VC_APF_IMPORTED_DATA_ARENA_USED_SIZE,
               "APF loader arena is too small");

static bool vc_apf_first_entry_spans_overlap(uint32_t left_base,
                                             uint32_t left_size,
                                             uint32_t right_base,
                                             uint32_t right_size) {
    return (uint64_t)left_base + left_size > right_base &&
           (uint64_t)right_base + right_size > left_base;
}

static bool vc_apf_first_entry_policy_valid(
    const vc_apf_first_entry_policy *policy) {
    uint64_t vm_end;

    if (policy == NULL ||
        policy->configured_fields != VC_APF_BOOT_CONFIG_ALL ||
        policy->vm_arena_base == 0u || policy->vm_arena_size == 0u ||
        (policy->vm_arena_base & (VC_APF_BOOT_VM_PAGE_SIZE - 1u)) != 0u ||
        (policy->vm_arena_size & (VC_APF_BOOT_VM_PAGE_SIZE - 1u)) != 0u ||
        policy->vm_arena_size / VC_APF_BOOT_VM_PAGE_SIZE >
            VC_APF_BOOT_VM_MAX_PAGES) {
        return false;
    }
    vm_end = (uint64_t)policy->vm_arena_base + policy->vm_arena_size;
    if (vm_end > VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE ||
        vc_apf_first_entry_spans_overlap(
            policy->vm_arena_base, policy->vm_arena_size,
            VC_APF_RETAIL_TITLE_BASE, VC_APF_RETAIL_TITLE_SIZE) ||
        vc_apf_first_entry_spans_overlap(
            policy->vm_arena_base, policy->vm_arena_size,
            VC_APF_STATIC_DISPATCH_BASE, VC_APF_STATIC_DISPATCH_SIZE) ||
        vc_apf_first_entry_spans_overlap(
            policy->vm_arena_base, policy->vm_arena_size,
            VC_APF_FIRST_ENTRY_STACK_BASE, VC_APF_FIRST_ENTRY_STACK_SIZE) ||
        vc_apf_first_entry_spans_overlap(
            policy->vm_arena_base, policy->vm_arena_size,
            VC_APF_FIRST_ENTRY_LOADER_ARENA_BASE,
            VC_APF_FIRST_ENTRY_LOADER_ARENA_SIZE)) {
        return false;
    }
    return true;
}

static const vc_apf_first_entry_import_binding *
vc_apf_first_entry_find_binding(uint32_t thunk_address) {
    size_t index;

    for (index = 0u; index < VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT;
         ++index) {
        if (vc_apf_frontier_bindings[index].thunk_address == thunk_address) {
            return &vc_apf_frontier_bindings[index];
        }
    }
    return NULL;
}

void vc_apf_first_entry_state_init(vc_apf_first_entry_state *state) {
    if (state != NULL) {
        memset(state, 0, sizeof(*state));
    }
}

const vc_apf_first_entry_import_binding *vc_apf_first_entry_bindings(
    size_t *binding_count) {
    if (binding_count != NULL) {
        *binding_count = VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT;
    }
    return vc_apf_frontier_bindings;
}

void vc_apf_first_entry_destroy(vc_apf_first_entry_state *state) {
    if (state == NULL) {
        return;
    }
    free(state->loader_thread);
    free(state->adapter_runtime);
    if (state->guest_address_space != NULL &&
        state->guest_address_space_byte_count != 0u) {
        (void)munmap(state->guest_address_space,
                     state->guest_address_space_byte_count);
    }
    memset(state, 0, sizeof(*state));
}

vc_apf_first_entry_status vc_apf_first_entry_prepare(
    vc_apf_first_entry_state *state,
    const vc_apf_first_entry_config *config) {
    vc_apf_imported_data_config imported_config;
    vc_apf_boot_leaf_config leaf_config;
    vc_apf_boot_leaf_status leaf_status;
    vc_apf_imported_data_status imported_status;
    void *mapping;
    int mapping_flags = MAP_PRIVATE | MAP_ANONYMOUS;

    if (state == NULL || config == NULL ||
        config->decoded_image_bytes == NULL ||
        config->raw_xex_prefix_bytes == NULL ||
        config->decoded_image_byte_count !=
            VC_APF_IMPORTED_DATA_IMAGE_SIZE ||
        config->raw_xex_prefix_byte_count <
            VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE ||
        config->instruction_budget == 0u ||
        config->function_dispatch_budget == 0u ||
        state->guest_address_space != NULL || state->prepared ||
        !vc_apf_first_entry_policy_valid(&config->policy)) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    if (SIZE_MAX < VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE) {
        return VC_APF_FIRST_ENTRY_UNSUPPORTED_HOST;
    }
#ifdef MAP_NORESERVE
    mapping_flags |= MAP_NORESERVE;
#endif
    mapping = mmap(NULL, (size_t)VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE,
                   PROT_READ | PROT_WRITE, mapping_flags, -1, 0);
    if (mapping == MAP_FAILED) {
        return VC_APF_FIRST_ENTRY_MAPPING_FAILED;
    }
    state->guest_address_space = mapping;
    state->guest_address_space_byte_count =
        (size_t)VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE;
#ifdef MADV_DONTDUMP
    (void)madvise(mapping,
                  (size_t)VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE,
                  MADV_DONTDUMP);
#endif

    memcpy(state->guest_address_space + VC_APF_IMPORTED_DATA_IMAGE_BASE,
           config->decoded_image_bytes, config->decoded_image_byte_count);
    memset(&imported_config, 0, sizeof(imported_config));
    imported_config.decoded_image_bytes =
        state->guest_address_space + VC_APF_IMPORTED_DATA_IMAGE_BASE;
    imported_config.decoded_image_guest_base =
        VC_APF_IMPORTED_DATA_IMAGE_BASE;
    imported_config.decoded_image_byte_count =
        VC_APF_IMPORTED_DATA_IMAGE_SIZE;
    imported_config.raw_xex_prefix_bytes = config->raw_xex_prefix_bytes;
    imported_config.raw_xex_prefix_byte_count =
        config->raw_xex_prefix_byte_count;
    imported_config.arena_bytes =
        state->guest_address_space + VC_APF_FIRST_ENTRY_LOADER_ARENA_BASE;
    imported_config.arena_guest_base = VC_APF_FIRST_ENTRY_LOADER_ARENA_BASE;
    imported_config.arena_byte_count = VC_APF_FIRST_ENTRY_LOADER_ARENA_SIZE;
    imported_config.debugger_enabled = false;
    imported_status = vc_apf_imported_data_bootstrap(
        &imported_config, &state->imported_data);
    if (imported_status != VC_APF_IMPORTED_DATA_OK) {
        vc_apf_first_entry_destroy(state);
        return VC_APF_FIRST_ENTRY_IMPORTED_DATA_FAILED;
    }
    imported_status = vc_apf_imported_data_probe_consumers(
        &imported_config, &state->imported_data,
        &state->imported_data_evidence);
    if (imported_status != VC_APF_IMPORTED_DATA_OK) {
        vc_apf_first_entry_destroy(state);
        return VC_APF_FIRST_ENTRY_IMPORTED_DATA_FAILED;
    }

    state->adapter_runtime = calloc(1u, sizeof(*state->adapter_runtime));
    state->loader_thread = calloc(1u, sizeof(*state->loader_thread));
    if (state->adapter_runtime == NULL || state->loader_thread == NULL) {
        vc_apf_first_entry_destroy(state);
        return VC_APF_FIRST_ENTRY_MAPPING_FAILED;
    }
    memset(&leaf_config, 0, sizeof(leaf_config));
    leaf_config.configured_fields = config->policy.configured_fields;
    leaf_config.process_type = config->policy.process_type;
    leaf_config.language = config->policy.language;
    leaf_config.av_pack = config->policy.av_pack;
    leaf_config.executable_system_flags =
        config->policy.executable_system_flags;
    leaf_config.secured_av_region = config->policy.secured_av_region;
    leaf_config.user_video_flags = config->policy.user_video_flags;
    leaf_config.vm_arena_base = config->policy.vm_arena_base;
    leaf_config.vm_arena_size = config->policy.vm_arena_size;
    leaf_config.vm_backing_bytes =
        state->guest_address_space + config->policy.vm_arena_base;
    leaf_config.vm_backing_byte_count = config->policy.vm_arena_size;
    leaf_config.vm_existing_range_count = 5u;
    leaf_config.vm_existing_ranges[0] = (vc_apf_boot_vm_existing_range){
        VC_APF_RETAIL_TITLE_BASE, VC_APF_RETAIL_TITLE_SIZE,
        VC_APF_BOOT_VM_RANGE_TITLE_IMAGE};
    leaf_config.vm_existing_ranges[1] = (vc_apf_boot_vm_existing_range){
        VC_APF_STATIC_DISPATCH_BASE, VC_APF_STATIC_DISPATCH_SIZE,
        VC_APF_BOOT_VM_RANGE_STATIC_DISPATCH};
    leaf_config.vm_existing_ranges[2] = (vc_apf_boot_vm_existing_range){
        VC_APF_RETAIL_IMPORT_THUNK_BASE, VC_APF_RETAIL_IMPORT_THUNK_SPAN,
        VC_APF_BOOT_VM_RANGE_IMPORT_THUNKS};
    leaf_config.vm_existing_ranges[3] = (vc_apf_boot_vm_existing_range){
        VC_APF_FIRST_ENTRY_STACK_BASE, VC_APF_FIRST_ENTRY_STACK_SIZE,
        VC_APF_BOOT_VM_RANGE_OTHER_MAPPING};
    leaf_config.vm_existing_ranges[4] = (vc_apf_boot_vm_existing_range){
        VC_APF_FIRST_ENTRY_LOADER_ARENA_BASE,
        VC_APF_FIRST_ENTRY_LOADER_ARENA_SIZE,
        VC_APF_BOOT_VM_RANGE_OTHER_MAPPING};
    leaf_status = vc_apf_boot_leaf_runtime_init(state->adapter_runtime,
                                                &leaf_config);
    if (leaf_status != VC_APF_BOOT_LEAF_OK) {
        vc_apf_first_entry_destroy(state);
        return VC_APF_FIRST_ENTRY_ADAPTER_FAILED;
    }
    vc_apf_boot_leaf_thread_init(state->loader_thread);
    leaf_status = vc_apf_boot_leaf_thread_attach(
        state->adapter_runtime, state->loader_thread,
        VC_APF_FIRST_ENTRY_THREAD_OBJECT);
    if (leaf_status != VC_APF_BOOT_LEAF_OK) {
        vc_apf_first_entry_destroy(state);
        return VC_APF_FIRST_ENTRY_ADAPTER_FAILED;
    }

    memset(&state->loader_context, 0, sizeof(state->loader_context));
    state->loader_context.gpr[1] = VC_APF_FIRST_ENTRY_STACK_TOP;
    state->guest_memory.bytes = state->guest_address_space;
    state->guest_memory.guest_base = 0u;
    state->guest_memory.byte_count =
        (size_t)VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE;
    state->budget.instruction_limit = config->instruction_budget;
    state->budget.function_dispatch_limit =
        config->function_dispatch_budget;
    state->bindings = vc_apf_frontier_bindings;
    state->binding_count = VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT;
    state->prepared = true;
    return VC_APF_FIRST_ENTRY_OK;
}

vc_apf_first_entry_status vc_apf_first_entry_consume_budget(
    vc_apf_first_entry_budget *budget,
    uint64_t instruction_count,
    uint64_t function_dispatch_count) {
    if (budget == NULL || budget->instruction_limit == 0u ||
        budget->function_dispatch_limit == 0u) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    if (budget->exhausted ||
        budget->instructions_consumed > budget->instruction_limit ||
        budget->function_dispatches_consumed >
            budget->function_dispatch_limit ||
        instruction_count >
            budget->instruction_limit - budget->instructions_consumed ||
        function_dispatch_count >
            budget->function_dispatch_limit -
                budget->function_dispatches_consumed) {
        budget->exhausted = true;
        return VC_APF_FIRST_ENTRY_BUDGET_EXHAUSTED;
    }
    budget->instructions_consumed += instruction_count;
    budget->function_dispatches_consumed += function_dispatch_count;
    return VC_APF_FIRST_ENTRY_OK;
}

vc_apf_first_entry_status vc_apf_first_entry_dispatch_import(
    vc_apf_first_entry_state *state,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk,
    vc_apf_boot_leaf_status *adapter_status) {
    vc_apf_boot_leaf_status status;
    vc_apf_first_entry_status budget_status;

    if (state == NULL || context == NULL || adapter_status == NULL ||
        !state->prepared || state->adapter_runtime == NULL ||
        state->loader_thread == NULL) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    if (vc_apf_first_entry_find_binding(import_thunk) == NULL) {
        return VC_APF_FIRST_ENTRY_UNKNOWN_IMPORT;
    }
    budget_status = vc_apf_first_entry_consume_budget(&state->budget, 0u, 1u);
    if (budget_status != VC_APF_FIRST_ENTRY_OK) {
        return budget_status;
    }
    status = vc_apf_boot_leaf_dispatch(
        state->adapter_runtime, state->loader_thread, &state->guest_memory,
        context, import_thunk);
    *adapter_status = status;
    if (import_thunk == VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK &&
        context->lr == VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN) {
        state->first_boundary_thunk = import_thunk;
        state->first_boundary_adapter_status = status;
    }
    return status == VC_APF_BOOT_LEAF_OK ? VC_APF_FIRST_ENTRY_OK
                                         : VC_APF_FIRST_ENTRY_ADAPTER_FAILED;
}

vc_apf_first_entry_status vc_apf_first_entry_probe_expected_boundary(
    vc_apf_first_entry_state *state) {
    vc_apf_guest_ppc_context context;
    vc_apf_boot_leaf_status adapter_status = VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
    vc_apf_first_entry_status status;

    if (state == NULL || !state->prepared ||
        !state->imported_data_evidence.sub_84bf1850_reaches_header_query ||
        state->imported_data_evidence.requested_key_present ||
        !state->imported_data_evidence.bounded_absent_key_result_is_null) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    memset(&context, 0, sizeof(context));
    context.lr = VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN;
    context.gpr[3] = state->imported_data.raw_xex_prefix;
    context.gpr[4] = VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE;
    status = vc_apf_first_entry_dispatch_import(
        state, &context, VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK,
        &adapter_status);
    if (status != VC_APF_FIRST_ENTRY_OK ||
        adapter_status != VC_APF_BOOT_LEAF_OK || context.gpr[3] != 0u) {
        return VC_APF_FIRST_ENTRY_ADAPTER_FAILED;
    }
    state->first_boundary_adapter_probed = true;
    return VC_APF_FIRST_ENTRY_OK;
}

void vc_apf_first_entry_readiness(
    const vc_apf_first_entry_state *state,
    vc_apf_first_entry_readiness_result *result) {
    if (result == NULL) {
        return;
    }
    memset(result, 0, sizeof(*result));
    result->exact_first_boundary_proved =
        state != NULL && state->prepared &&
        state->imported_data_evidence.sub_84bf1850_reaches_header_query &&
        !state->imported_data_evidence.callback_dispatch_possible;
    result->first_boundary_adapter_probed =
        state != NULL && state->first_boundary_adapter_probed;
    result->child_containment_available = true;
    result->function_budget_ledger_available = true;
    result->instruction_budget_ledger_available = true;
    /*
     * PORTME: regenerate one isolated corpus with both opcode and switch-tail
     * candidates applied before this blocker may be removed.
     */
    result->blockers[result->blocker_count++] =
        VC_APF_FIRST_ENTRY_BLOCKER_COMPOSED_DERIVED_CORPUS;
    if (state == NULL || !state->generated_dispatch_installed ||
        state->generated_dispatch_mapping_count != 60731u) {
        result->blockers[result->blocker_count++] =
            VC_APF_FIRST_ENTRY_BLOCKER_GENERATED_DISPATCH_BRIDGE_LINK;
    }
    /*
     * PORTME: instrument every executed guest instruction in the derived
     * generated corpus; owning a tested counter is not instrumentation.
     */
    result->blockers[result->blocker_count++] =
        VC_APF_FIRST_ENTRY_BLOCKER_INSTRUCTION_BUDGET_INSTRUMENTATION;
    result->entry_call_authorized = false;
    result->entry_called = false;
}

static int64_t vc_apf_first_entry_monotonic_milliseconds(void) {
    struct timespec now;

    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        return -1;
    }
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

vc_apf_first_entry_status vc_apf_first_entry_run_contained(
    vc_apf_first_entry_child_callback callback,
    void *opaque,
    uint32_t timeout_milliseconds,
    vc_apf_first_entry_child_result *result) {
    int descriptors[2];
    pid_t child;
    int wait_status = 0;
    int64_t deadline;
    int callback_result = 0;
    ssize_t bytes_read = 0;

    if (callback == NULL || result == NULL || timeout_milliseconds == 0u) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    memset(result, 0, sizeof(*result));
    if (pipe(descriptors) != 0) {
        return VC_APF_FIRST_ENTRY_CONTAINMENT_FAILED;
    }
    child = fork();
    if (child < 0) {
        (void)close(descriptors[0]);
        (void)close(descriptors[1]);
        return VC_APF_FIRST_ENTRY_CONTAINMENT_FAILED;
    }
    if (child == 0) {
        ssize_t written;
        (void)close(descriptors[0]);
        callback_result = callback(opaque);
        written = write(descriptors[1], &callback_result,
                        sizeof(callback_result));
        (void)written;
        (void)close(descriptors[1]);
        _exit(0);
    }

    (void)close(descriptors[1]);
    deadline = vc_apf_first_entry_monotonic_milliseconds();
    if (deadline < 0) {
        (void)kill(child, SIGKILL);
        (void)waitpid(child, NULL, 0);
        (void)close(descriptors[0]);
        return VC_APF_FIRST_ENTRY_CONTAINMENT_FAILED;
    }
    deadline += timeout_milliseconds;
    for (;;) {
        struct pollfd descriptor;
        int64_t now = vc_apf_first_entry_monotonic_milliseconds();
        int remaining;
        int poll_status;

        if (now < 0) {
            remaining = 0;
        } else if (now >= deadline) {
            remaining = 0;
        } else {
            const int64_t delta = deadline - now;
            remaining = delta > 2147483647 ? 2147483647 : (int)delta;
        }
        descriptor.fd = descriptors[0];
        descriptor.events = POLLIN | POLLHUP;
        descriptor.revents = 0;
        poll_status = poll(&descriptor, 1u, remaining);
        if (poll_status > 0) {
            break;
        }
        if (poll_status == 0) {
            (void)kill(child, SIGKILL);
            while (waitpid(child, &wait_status, 0) < 0 && errno == EINTR) {
            }
            (void)close(descriptors[0]);
            result->outcome = VC_APF_FIRST_ENTRY_CHILD_TIMED_OUT;
            result->signal_number = SIGKILL;
            return VC_APF_FIRST_ENTRY_OK;
        }
        if (errno != EINTR) {
            (void)kill(child, SIGKILL);
            (void)waitpid(child, NULL, 0);
            (void)close(descriptors[0]);
            return VC_APF_FIRST_ENTRY_CONTAINMENT_FAILED;
        }
    }
    do {
        bytes_read = read(descriptors[0], &callback_result,
                          sizeof(callback_result));
    } while (bytes_read < 0 && errno == EINTR);
    (void)close(descriptors[0]);
    while (waitpid(child, &wait_status, 0) < 0 && errno == EINTR) {
    }
    if (WIFSIGNALED(wait_status)) {
        result->outcome = VC_APF_FIRST_ENTRY_CHILD_SIGNALED;
        result->signal_number = WTERMSIG(wait_status);
        return VC_APF_FIRST_ENTRY_OK;
    }
    if (!WIFEXITED(wait_status) || WEXITSTATUS(wait_status) != 0 ||
        bytes_read != (ssize_t)sizeof(callback_result)) {
        return VC_APF_FIRST_ENTRY_CONTAINMENT_FAILED;
    }
    result->outcome = VC_APF_FIRST_ENTRY_CHILD_EXITED;
    result->callback_result = callback_result;
    return VC_APF_FIRST_ENTRY_OK;
}

const char *vc_apf_first_entry_status_name(vc_apf_first_entry_status status) {
    switch (status) {
    case VC_APF_FIRST_ENTRY_OK:
        return "ok";
    case VC_APF_FIRST_ENTRY_INVALID_ARGUMENT:
        return "invalid_argument";
    case VC_APF_FIRST_ENTRY_UNSUPPORTED_HOST:
        return "unsupported_host";
    case VC_APF_FIRST_ENTRY_MAPPING_FAILED:
        return "mapping_failed";
    case VC_APF_FIRST_ENTRY_IMPORTED_DATA_FAILED:
        return "imported_data_failed";
    case VC_APF_FIRST_ENTRY_ADAPTER_FAILED:
        return "adapter_failed";
    case VC_APF_FIRST_ENTRY_UNKNOWN_IMPORT:
        return "unknown_import";
    case VC_APF_FIRST_ENTRY_BUDGET_EXHAUSTED:
        return "budget_exhausted";
    case VC_APF_FIRST_ENTRY_CONTAINMENT_FAILED:
        return "containment_failed";
    case VC_APF_FIRST_ENTRY_NOT_AUTHORIZED:
        return "not_authorized";
    default:
        return "unknown";
    }
}

const char *vc_apf_first_entry_blocker_name(
    vc_apf_first_entry_blocker blocker) {
    switch (blocker) {
    case VC_APF_FIRST_ENTRY_BLOCKER_NONE:
        return "none";
    case VC_APF_FIRST_ENTRY_BLOCKER_COMPOSED_DERIVED_CORPUS:
        return "composed_derived_corpus";
    case VC_APF_FIRST_ENTRY_BLOCKER_GENERATED_DISPATCH_BRIDGE_LINK:
        return "generated_dispatch_bridge_link";
    case VC_APF_FIRST_ENTRY_BLOCKER_INSTRUCTION_BUDGET_INSTRUMENTATION:
        return "instruction_budget_instrumentation";
    default:
        return "unknown";
    }
}
