#ifndef VC_STATIC_RUNTIME_APF_FIRST_ENTRY_GATE_H
#define VC_STATIC_RUNTIME_APF_FIRST_ENTRY_GATE_H

#include "static_runtime/apf_boot_leaf_adapters.h"
#include "static_runtime/apf_imported_data_bootstrap.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Isolated APF first-entry integration gate.
 *
 * This module deliberately has no function that calls _xstart.  It owns a
 * sparse 4 GiB guest mapping, installs the exact decoded image and the two
 * proved imported-data objects, initializes loader-owned stack/thread state,
 * and binds the 30 current frontier imports to the typed leaf dispatcher.
 * Entry remains fail-closed until vc_apf_first_entry_readiness reports no
 * ordered blockers and a separately instrumented generated-code driver exists.
 */

#define VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE UINT64_C(0x100000000)
#define VC_APF_FIRST_ENTRY_ADDRESS 0x84BE9D08u
#define VC_APF_FIRST_ENTRY_FIRST_IMPORT_CALL 0x84BF1888u
#define VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN 0x84BF188Cu
#define VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK \
    VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD

#define VC_APF_FIRST_ENTRY_STACK_BASE 0x70000000u
#define VC_APF_FIRST_ENTRY_STACK_SIZE 0x00020000u
#define VC_APF_FIRST_ENTRY_STACK_TOP \
    (VC_APF_FIRST_ENTRY_STACK_BASE + VC_APF_FIRST_ENTRY_STACK_SIZE)
#define VC_APF_FIRST_ENTRY_LOADER_ARENA_BASE 0x70020000u
#define VC_APF_FIRST_ENTRY_LOADER_ARENA_SIZE 0x00001000u
#define VC_APF_FIRST_ENTRY_THREAD_OBJECT 0x70020200u
#define VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT 30u
#define VC_APF_FIRST_ENTRY_MAX_BLOCKERS 8u

typedef enum vc_apf_first_entry_status {
    VC_APF_FIRST_ENTRY_OK = 0,
    VC_APF_FIRST_ENTRY_INVALID_ARGUMENT,
    VC_APF_FIRST_ENTRY_UNSUPPORTED_HOST,
    VC_APF_FIRST_ENTRY_MAPPING_FAILED,
    VC_APF_FIRST_ENTRY_IMPORTED_DATA_FAILED,
    VC_APF_FIRST_ENTRY_ADAPTER_FAILED,
    VC_APF_FIRST_ENTRY_UNKNOWN_IMPORT,
    VC_APF_FIRST_ENTRY_BUDGET_EXHAUSTED,
    VC_APF_FIRST_ENTRY_CONTAINMENT_FAILED,
    VC_APF_FIRST_ENTRY_NOT_AUTHORIZED
} vc_apf_first_entry_status;

typedef enum vc_apf_first_entry_import_class {
    VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE = 1,
    VC_APF_FIRST_ENTRY_IMPORT_TERMINAL,
    VC_APF_FIRST_ENTRY_IMPORT_EXCEPTION_REQUIRED,
    VC_APF_FIRST_ENTRY_IMPORT_THREAD_CREATE_REQUIRED
} vc_apf_first_entry_import_class;

typedef struct vc_apf_first_entry_import_binding {
    uint32_t thunk_address;
    const char *name;
    vc_apf_first_entry_import_class classification;
} vc_apf_first_entry_import_binding;

typedef struct vc_apf_first_entry_budget {
    uint64_t instruction_limit;
    uint64_t function_dispatch_limit;
    uint64_t instructions_consumed;
    uint64_t function_dispatches_consumed;
    bool exhausted;
} vc_apf_first_entry_budget;

typedef struct vc_apf_first_entry_policy {
    uint32_t configured_fields;
    uint32_t process_type;
    uint32_t language;
    uint32_t av_pack;
    uint32_t executable_system_flags;
    uint32_t secured_av_region;
    uint32_t user_video_flags;
    uint32_t vm_arena_base;
    uint32_t vm_arena_size;
} vc_apf_first_entry_policy;

typedef struct vc_apf_first_entry_config {
    const uint8_t *decoded_image_bytes;
    size_t decoded_image_byte_count;
    const uint8_t *raw_xex_prefix_bytes;
    size_t raw_xex_prefix_byte_count;
    vc_apf_first_entry_policy policy;
    uint64_t instruction_budget;
    uint64_t function_dispatch_budget;
} vc_apf_first_entry_config;

typedef enum vc_apf_first_entry_blocker {
    VC_APF_FIRST_ENTRY_BLOCKER_NONE = 0,
    VC_APF_FIRST_ENTRY_BLOCKER_COMPOSED_DERIVED_CORPUS,
    VC_APF_FIRST_ENTRY_BLOCKER_GENERATED_DISPATCH_BRIDGE_LINK,
    VC_APF_FIRST_ENTRY_BLOCKER_INSTRUCTION_BUDGET_INSTRUMENTATION
} vc_apf_first_entry_blocker;

typedef struct vc_apf_first_entry_readiness_result {
    bool entry_call_authorized;
    bool entry_called;
    bool exact_first_boundary_proved;
    bool first_boundary_adapter_probed;
    bool child_containment_available;
    bool function_budget_ledger_available;
    bool instruction_budget_ledger_available;
    size_t blocker_count;
    vc_apf_first_entry_blocker blockers[VC_APF_FIRST_ENTRY_MAX_BLOCKERS];
} vc_apf_first_entry_readiness_result;

typedef enum vc_apf_first_entry_child_outcome {
    VC_APF_FIRST_ENTRY_CHILD_EXITED = 0,
    VC_APF_FIRST_ENTRY_CHILD_SIGNALED,
    VC_APF_FIRST_ENTRY_CHILD_TIMED_OUT
} vc_apf_first_entry_child_outcome;

typedef struct vc_apf_first_entry_child_result {
    vc_apf_first_entry_child_outcome outcome;
    int callback_result;
    int signal_number;
} vc_apf_first_entry_child_result;

typedef int (*vc_apf_first_entry_child_callback)(void *opaque);

typedef struct vc_apf_first_entry_state {
    uint8_t *guest_address_space;
    size_t guest_address_space_byte_count;
    vc_apf_imported_data_result imported_data;
    vc_apf_imported_data_consumer_evidence imported_data_evidence;
    vc_apf_boot_leaf_runtime *adapter_runtime;
    vc_apf_guest_thread *loader_thread;
    vc_apf_guest_memory guest_memory;
    vc_apf_guest_ppc_context loader_context;
    vc_apf_first_entry_budget budget;
    const vc_apf_first_entry_import_binding *bindings;
    size_t binding_count;
    bool prepared;
    bool generated_dispatch_installed;
    size_t generated_dispatch_mapping_count;
    bool first_boundary_adapter_probed;
    uint32_t first_boundary_thunk;
    vc_apf_boot_leaf_status first_boundary_adapter_status;
} vc_apf_first_entry_state;

void vc_apf_first_entry_state_init(vc_apf_first_entry_state *state);

vc_apf_first_entry_status vc_apf_first_entry_prepare(
    vc_apf_first_entry_state *state,
    const vc_apf_first_entry_config *config);

void vc_apf_first_entry_destroy(vc_apf_first_entry_state *state);

const vc_apf_first_entry_import_binding *vc_apf_first_entry_bindings(
    size_t *binding_count);

vc_apf_first_entry_status vc_apf_first_entry_consume_budget(
    vc_apf_first_entry_budget *budget,
    uint64_t instruction_count,
    uint64_t function_dispatch_count);

vc_apf_first_entry_status vc_apf_first_entry_dispatch_import(
    vc_apf_first_entry_state *state,
    vc_apf_guest_ppc_context *context,
    uint32_t import_thunk,
    vc_apf_boot_leaf_status *adapter_status);

/*
 * Exercise the exact first import with the bootstrap-produced pointer and
 * retail key.  This calls only the typed adapter; it does not call _xstart or
 * any translated APF function.
 */
vc_apf_first_entry_status vc_apf_first_entry_probe_expected_boundary(
    vc_apf_first_entry_state *state);

void vc_apf_first_entry_readiness(
    const vc_apf_first_entry_state *state,
    vc_apf_first_entry_readiness_result *result);

vc_apf_first_entry_status vc_apf_first_entry_run_contained(
    vc_apf_first_entry_child_callback callback,
    void *opaque,
    uint32_t timeout_milliseconds,
    vc_apf_first_entry_child_result *result);

const char *vc_apf_first_entry_status_name(vc_apf_first_entry_status status);
const char *vc_apf_first_entry_blocker_name(
    vc_apf_first_entry_blocker blocker);

#ifdef __cplusplus
}
#endif

#endif
