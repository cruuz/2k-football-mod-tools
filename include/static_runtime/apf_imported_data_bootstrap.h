#ifndef VC_STATIC_RUNTIME_APF_IMPORTED_DATA_BOOTSTRAP_H
#define VC_STATIC_RUNTIME_APF_IMPORTED_DATA_BOOTSTRAP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Isolated APF 2K8 imported-data bootstrap.
 *
 * This is a pre-entry loader helper, not a title runner. It seeds only the two
 * imported xboxkrnl variables consumed by the current 458-node augmented
 * frontier. The other eleven retail ordinal words must remain untouched.
 */

#define VC_APF_IMPORTED_DATA_IMAGE_BASE 0x82000000u
#define VC_APF_IMPORTED_DATA_IMAGE_SIZE 0x03380000u
#define VC_APF_IMPORTED_DATA_DISPATCH_BASE 0x85380000u
#define VC_APF_IMPORTED_DATA_DISPATCH_SIZE 0x00DB3000u
#define VC_APF_IMPORTED_DATA_ARENA_ALIGNMENT 0x00001000u

#define VC_APF_IMPORTED_DATA_XEX_SLOT 0x820007ACu
#define VC_APF_IMPORTED_DATA_DEBUG_SLOT 0x82000940u
#define VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE 144u
#define VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE 0x00020401u

/* Fixed, non-overlapping objects inside the caller-owned guest arena. */
#define VC_APF_IMPORTED_DATA_XEX_CELL_OFFSET 0x000u
#define VC_APF_IMPORTED_DATA_MODULE_OFFSET 0x010u
#define VC_APF_IMPORTED_DATA_MODULE_SIZE 0x064u
#define VC_APF_IMPORTED_DATA_MODULE_XEX_HEADER_OFFSET 0x058u
#define VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET 0x080u
#define VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET 0x100u
#define VC_APF_IMPORTED_DATA_ARENA_USED_SIZE 0x190u

typedef enum vc_apf_imported_data_status {
    VC_APF_IMPORTED_DATA_OK = 0,
    VC_APF_IMPORTED_DATA_INVALID_ARGUMENT,
    VC_APF_IMPORTED_DATA_UNSUPPORTED_CONFIGURATION,
    VC_APF_IMPORTED_DATA_WRONG_IMAGE,
    VC_APF_IMPORTED_DATA_WRONG_XEX_PREFIX,
    VC_APF_IMPORTED_DATA_BOUNDS,
    VC_APF_IMPORTED_DATA_OVERLAP,
    VC_APF_IMPORTED_DATA_ARENA_NOT_EMPTY,
    VC_APF_IMPORTED_DATA_GUEST_STATE
} vc_apf_imported_data_status;

typedef struct vc_apf_imported_data_config {
    uint8_t *decoded_image_bytes;
    uint32_t decoded_image_guest_base;
    size_t decoded_image_byte_count;

    /* First 144 bytes of the untouched raw default.xex. */
    const uint8_t *raw_xex_prefix_bytes;
    size_t raw_xex_prefix_byte_count;

    /* Fresh, zero-filled storage owned for the lifetime of the guest loader. */
    uint8_t *arena_bytes;
    uint32_t arena_guest_base;
    size_t arena_byte_count;

    /* This bounded implementation supports only Xenia's no-debugger form. */
    bool debugger_enabled;
} vc_apf_imported_data_config;

typedef struct vc_apf_imported_data_result {
    uint32_t xex_export_cell;
    uint32_t executable_module_object;
    uint32_t raw_xex_prefix;
    uint32_t debug_monitor_export_cell;
    uint32_t seeded_slot_count;
    uint32_t preserved_ordinal_slot_count;
    uint32_t copied_xex_prefix_byte_count;
} vc_apf_imported_data_result;

typedef struct vc_apf_imported_data_consumer_evidence {
    uint32_t sub_84bf1850_slot_load_address;
    uint32_t sub_84bf1850_header_load_address;
    uint32_t rtl_image_xex_header_field_call_address;
    uint32_t rtl_image_xex_header_field_return_address;
    uint32_t requested_xex_key;
    uint32_t resolved_xex_header_address;
    bool sub_84bf1850_reaches_header_query;
    bool requested_key_present;
    bool bounded_absent_key_result_is_null;

    uint32_t sub_84bf1950_slot_load_address;
    uint32_t sub_84bf1950_callback_call_address;
    uint32_t resolved_debug_monitor_object;
    bool debugger_disabled;
    bool callback_field_read;
    bool callback_dispatch_possible;
} vc_apf_imported_data_consumer_evidence;

vc_apf_imported_data_status vc_apf_imported_data_bootstrap(
    const vc_apf_imported_data_config *config,
    vc_apf_imported_data_result *result);

vc_apf_imported_data_status vc_apf_imported_data_probe_consumers(
    const vc_apf_imported_data_config *config,
    const vc_apf_imported_data_result *result,
    vc_apf_imported_data_consumer_evidence *evidence);

const char *vc_apf_imported_data_status_name(
    vc_apf_imported_data_status status);

#ifdef __cplusplus
}
#endif

#endif
