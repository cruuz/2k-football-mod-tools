#include "ppc_recomp_shared.h"
#include "static_runtime/apf_first_entry_xenon_bridge.h"

#include <cstring>

namespace {

thread_local vc_apf_first_entry_state *vc_apf_bound_state = nullptr;

#define VC_APF_GPR_CASES(operation)                                          \
    operation(0) operation(1) operation(2) operation(3) operation(4)        \
    operation(5) operation(6) operation(7) operation(8) operation(9)        \
    operation(10) operation(11) operation(12) operation(13) operation(14)   \
    operation(15) operation(16) operation(17) operation(18) operation(19)   \
    operation(20) operation(21) operation(22) operation(23) operation(24)   \
    operation(25) operation(26) operation(27) operation(28) operation(29)   \
    operation(30) operation(31)

std::uint64_t read_gpr(const PPCContext &context, unsigned int index) {
    switch (index) {
#define VC_APF_READ_CASE(number) case number: return context.r##number.u64;
        VC_APF_GPR_CASES(VC_APF_READ_CASE)
#undef VC_APF_READ_CASE
    default:
        return 0u;
    }
}

void write_gpr(PPCContext &context, unsigned int index, std::uint64_t value) {
    switch (index) {
#define VC_APF_WRITE_CASE(number)                                            \
    case number:                                                             \
        context.r##number.u64 = value;                                       \
        return;
        VC_APF_GPR_CASES(VC_APF_WRITE_CASE)
#undef VC_APF_WRITE_CASE
    default:
        return;
    }
}

[[noreturn]] void dispatch_and_stop(PPCContext &context, std::uint8_t *base,
                                    std::uint32_t import_thunk) {
    vc_apf_guest_ppc_context adapter_context{};
    vc_apf_boot_leaf_status adapter_status = VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
    vc_apf_first_entry_status gate_status;
    unsigned int index;

    if (vc_apf_bound_state == nullptr ||
        base != vc_apf_bound_state->guest_address_space) {
        throw vc_apf_first_entry_boundary_stop{
            VC_APF_FIRST_ENTRY_INVALID_ARGUMENT,
            VC_APF_BOOT_LEAF_INVALID_ARGUMENT, import_thunk};
    }
    for (index = 0u; index < 32u; ++index) {
        adapter_context.gpr[index] = read_gpr(context, index);
    }
    adapter_context.lr = static_cast<std::uint32_t>(context.lr);
    gate_status = vc_apf_first_entry_dispatch_import(
        vc_apf_bound_state, &adapter_context, import_thunk, &adapter_status);
    for (index = 0u; index < 32u; ++index) {
        write_gpr(context, index, adapter_context.gpr[index]);
    }
    context.lr = adapter_context.lr;
    throw vc_apf_first_entry_boundary_stop{
        gate_status, adapter_status, import_thunk};
}

PPCFunc *expected_bridge(std::uint32_t thunk) {
    switch (thunk) {
    case VC_APF_THUNK_XGET_LANGUAGE: return __imp__XGetLanguage;
    case VC_APF_THUNK_XGET_AV_PACK: return __imp__XGetAVPack;
    case VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION:
        return __imp__RtlInitializeCriticalSection;
    case VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION:
        return __imp__RtlEnterCriticalSection;
    case VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION:
        return __imp__RtlLeaveCriticalSection;
    case VC_APF_THUNK_XAM_LOADER_TERMINATE_TITLE:
        return __imp__XamLoaderTerminateTitle;
    case VC_APF_THUNK_RTL_INIT_ANSI_STRING: return __imp__RtlInitAnsiString;
    case VC_APF_THUNK_KE_BUG_CHECK: return __imp__KeBugCheck;
    case VC_APF_THUNK_NT_CREATE_EVENT: return __imp__NtCreateEvent;
    case VC_APF_THUNK_NT_CLOSE: return __imp__NtClose;
    case VC_APF_THUNK_EX_GET_XCONFIG_SETTING:
        return __imp__ExGetXConfigSetting;
    case VC_APF_THUNK_DBG_PRINT: return __imp__DbgPrint;
    case VC_APF_THUNK_KE_TLS_ALLOC: return __imp__KeTlsAlloc;
    case VC_APF_THUNK_KE_TLS_GET_VALUE: return __imp__KeTlsGetValue;
    case VC_APF_THUNK_KE_TLS_SET_VALUE: return __imp__KeTlsSetValue;
    case VC_APF_THUNK_KE_TLS_FREE: return __imp__KeTlsFree;
    case VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE:
        return __imp__XexCheckExecutablePrivilege;
    case VC_APF_THUNK_KE_BUG_CHECK_EX: return __imp__KeBugCheckEx;
    case VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE:
        return __imp__KeGetCurrentProcessType;
    case VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG:
        return __imp__RtlCompareMemoryUlong;
    case VC_APF_THUNK_RTL_RAISE_EXCEPTION:
        return __imp__RtlRaiseException;
    case VC_APF_THUNK_EX_CREATE_THREAD: return __imp__ExCreateThread;
    case VC_APF_THUNK_HAL_RETURN_TO_FIRMWARE:
        return __imp__HalReturnToFirmware;
    case VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD:
        return __imp__RtlImageXexHeaderField;
    case VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY:
        return __imp__NtAllocateVirtualMemory;
    case VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY:
        return __imp__NtFreeVirtualMemory;
    case VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY:
        return __imp__NtQueryVirtualMemory;
    case VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX:
        return __imp__NtWaitForSingleObjectEx;
    case VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR:
        return __imp__RtlNtStatusToDosError;
    case VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX:
        return __imp__XamShowMessageBoxUIEx;
    default: return nullptr;
    }
}

#define VC_APF_DEFINE_IMPORT(symbol, thunk)                                  \
    PPC_FUNC(symbol) { dispatch_and_stop(ctx, base, thunk); }

} // namespace

vc_apf_first_entry_status vc_apf_first_entry_xenon_bridge_bind(
    vc_apf_first_entry_state *state) {
    if (state == nullptr || !state->prepared ||
        state->guest_address_space == nullptr || vc_apf_bound_state != nullptr) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    vc_apf_bound_state = state;
    return VC_APF_FIRST_ENTRY_OK;
}

void vc_apf_first_entry_xenon_bridge_unbind() {
    vc_apf_bound_state = nullptr;
}

vc_apf_first_entry_status vc_apf_first_entry_xenon_context_init(
    PPCContext *context) {
    if (context == nullptr) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    *context = PPCContext{};
    context->r1.u64 = VC_APF_FIRST_ENTRY_STACK_TOP;
    context->lr = 0u;
    return VC_APF_FIRST_ENTRY_OK;
}

vc_apf_first_entry_status vc_apf_first_entry_xenon_install_dispatch(
    vc_apf_first_entry_state *state,
    const PPCFuncMapping *mappings,
    std::size_t expected_mapping_count) {
    const vc_apf_first_entry_import_binding *bindings;
    std::size_t binding_count = 0u;
    std::size_t mapping_index;
    std::size_t found_bindings = 0u;

    if (state == nullptr || !state->prepared || mappings == nullptr ||
        expected_mapping_count != 60731u ||
        state->generated_dispatch_installed) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    bindings = vc_apf_first_entry_bindings(&binding_count);
    for (mapping_index = 0u; mapping_index < expected_mapping_count;
         ++mapping_index) {
        const std::uint64_t guest = mappings[mapping_index].guest;
        std::uint64_t lookup_address;

        if (mappings[mapping_index].host == nullptr ||
            guest < PPC_CODE_BASE || guest >= PPC_CODE_BASE + PPC_CODE_SIZE) {
            return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
        }
        lookup_address = PPC_IMAGE_BASE + PPC_IMAGE_SIZE +
                         (guest - PPC_CODE_BASE) * 2u;
        if (lookup_address < VC_APF_IMPORTED_DATA_DISPATCH_BASE ||
            lookup_address + sizeof(PPCFunc *) >
                static_cast<std::uint64_t>(
                    VC_APF_IMPORTED_DATA_DISPATCH_BASE) +
                    VC_APF_IMPORTED_DATA_DISPATCH_SIZE) {
            return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
        }
        std::memcpy(state->guest_address_space + lookup_address,
                    &mappings[mapping_index].host, sizeof(PPCFunc *));
        for (std::size_t binding_index = 0u;
             binding_index < binding_count; ++binding_index) {
            if (guest == bindings[binding_index].thunk_address) {
                if (mappings[mapping_index].host != expected_bridge(
                        bindings[binding_index].thunk_address)) {
                    return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
                }
                ++found_bindings;
            }
        }
    }
    if (mappings[expected_mapping_count].host != nullptr ||
        found_bindings != binding_count) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    state->generated_dispatch_installed = true;
    state->generated_dispatch_mapping_count = expected_mapping_count;
    return VC_APF_FIRST_ENTRY_OK;
}

VC_APF_DEFINE_IMPORT(__imp__XGetLanguage, VC_APF_THUNK_XGET_LANGUAGE)
VC_APF_DEFINE_IMPORT(__imp__XGetAVPack, VC_APF_THUNK_XGET_AV_PACK)
VC_APF_DEFINE_IMPORT(__imp__RtlInitializeCriticalSection,
                     VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION)
VC_APF_DEFINE_IMPORT(__imp__RtlEnterCriticalSection,
                     VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION)
VC_APF_DEFINE_IMPORT(__imp__RtlLeaveCriticalSection,
                     VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION)
VC_APF_DEFINE_IMPORT(__imp__XamLoaderTerminateTitle,
                     VC_APF_THUNK_XAM_LOADER_TERMINATE_TITLE)
VC_APF_DEFINE_IMPORT(__imp__RtlInitAnsiString,
                     VC_APF_THUNK_RTL_INIT_ANSI_STRING)
VC_APF_DEFINE_IMPORT(__imp__KeBugCheck, VC_APF_THUNK_KE_BUG_CHECK)
VC_APF_DEFINE_IMPORT(__imp__NtCreateEvent, VC_APF_THUNK_NT_CREATE_EVENT)
VC_APF_DEFINE_IMPORT(__imp__NtClose, VC_APF_THUNK_NT_CLOSE)
VC_APF_DEFINE_IMPORT(__imp__ExGetXConfigSetting,
                     VC_APF_THUNK_EX_GET_XCONFIG_SETTING)
VC_APF_DEFINE_IMPORT(__imp__DbgPrint, VC_APF_THUNK_DBG_PRINT)
VC_APF_DEFINE_IMPORT(__imp__KeTlsAlloc, VC_APF_THUNK_KE_TLS_ALLOC)
VC_APF_DEFINE_IMPORT(__imp__KeTlsGetValue, VC_APF_THUNK_KE_TLS_GET_VALUE)
VC_APF_DEFINE_IMPORT(__imp__KeTlsSetValue, VC_APF_THUNK_KE_TLS_SET_VALUE)
VC_APF_DEFINE_IMPORT(__imp__KeTlsFree, VC_APF_THUNK_KE_TLS_FREE)
VC_APF_DEFINE_IMPORT(__imp__XexCheckExecutablePrivilege,
                     VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE)
VC_APF_DEFINE_IMPORT(__imp__KeBugCheckEx, VC_APF_THUNK_KE_BUG_CHECK_EX)
VC_APF_DEFINE_IMPORT(__imp__KeGetCurrentProcessType,
                     VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE)
VC_APF_DEFINE_IMPORT(__imp__RtlCompareMemoryUlong,
                     VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG)
VC_APF_DEFINE_IMPORT(__imp__RtlRaiseException,
                     VC_APF_THUNK_RTL_RAISE_EXCEPTION)
VC_APF_DEFINE_IMPORT(__imp__ExCreateThread, VC_APF_THUNK_EX_CREATE_THREAD)
VC_APF_DEFINE_IMPORT(__imp__HalReturnToFirmware,
                     VC_APF_THUNK_HAL_RETURN_TO_FIRMWARE)
VC_APF_DEFINE_IMPORT(__imp__RtlImageXexHeaderField,
                     VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD)
VC_APF_DEFINE_IMPORT(__imp__NtAllocateVirtualMemory,
                     VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY)
VC_APF_DEFINE_IMPORT(__imp__NtFreeVirtualMemory,
                     VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY)
VC_APF_DEFINE_IMPORT(__imp__NtQueryVirtualMemory,
                     VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY)
VC_APF_DEFINE_IMPORT(__imp__NtWaitForSingleObjectEx,
                     VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX)
VC_APF_DEFINE_IMPORT(__imp__RtlNtStatusToDosError,
                     VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR)
VC_APF_DEFINE_IMPORT(__imp__XamShowMessageBoxUIEx,
                     VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX)

#undef VC_APF_DEFINE_IMPORT
