#include "static_runtime/apf_boot_leaf_adapters.h"
#include "static_runtime/apf_imported_data_bootstrap.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            fprintf(stderr, "check failed at %s:%d: %s\n", __FILE__,       \
                    __LINE__, #condition);                                   \
            return 1;                                                        \
        }                                                                    \
    } while (0)

typedef struct slot_signature {
    uint32_t address;
    uint32_t ordinal;
} slot_signature;

static const slot_signature imported_slots[] = {
    {0x82000744u, 0x000101AEu}, {0x820007ACu, 0x00010193u},
    {0x820007CCu, 0x000100ADu}, {0x8200080Cu, 0x0001001Cu},
    {0x8200081Cu, 0x00010017u}, {0x82000828u, 0x0001000Eu},
    {0x82000870u, 0x000101C1u}, {0x82000888u, 0x000101C0u},
    {0x820008BCu, 0x00010158u}, {0x820008D8u, 0x0001001Bu},
    {0x82000938u, 0x000101BEu}, {0x8200093Cu, 0x00010266u},
    {0x82000940u, 0x00010059u},
};

static uint32_t load_be_u32(const uint8_t *bytes) {
    return ((uint32_t)bytes[0] << 24u) | ((uint32_t)bytes[1] << 16u) |
           ((uint32_t)bytes[2] << 8u) | (uint32_t)bytes[3];
}

static uint8_t *read_exact_file(const char *path, size_t expected_size) {
    FILE *stream = fopen(path, "rb");
    uint8_t *bytes;
    size_t count;
    int trailing;
    if (stream == NULL) {
        return NULL;
    }
    bytes = (uint8_t *)malloc(expected_size);
    if (bytes == NULL) {
        fclose(stream);
        return NULL;
    }
    count = fread(bytes, 1u, expected_size, stream);
    trailing = fgetc(stream);
    if (count != expected_size || trailing != EOF || fclose(stream) != 0) {
        free(bytes);
        return NULL;
    }
    return bytes;
}

static uint8_t *read_file_prefix(const char *path, size_t prefix_size) {
    FILE *stream = fopen(path, "rb");
    uint8_t *bytes;
    size_t count;
    if (stream == NULL) {
        return NULL;
    }
    bytes = (uint8_t *)malloc(prefix_size);
    if (bytes == NULL) {
        fclose(stream);
        return NULL;
    }
    count = fread(bytes, 1u, prefix_size, stream);
    if (count != prefix_size || fclose(stream) != 0) {
        free(bytes);
        return NULL;
    }
    return bytes;
}

static void configure_leaf_runtime(vc_apf_boot_leaf_config *config,
                                   uint8_t *vm_backing,
                                   size_t vm_backing_size) {
    memset(config, 0, sizeof(*config));
    config->configured_fields = VC_APF_BOOT_CONFIG_ALL;
    config->process_type = 1u;
    config->language = 1u;
    config->av_pack = 6u;
    config->executable_system_flags = 0x00000200u;
    config->secured_av_region = 0x00000300u;
    config->user_video_flags = 0x00800000u;
    config->vm_arena_base = 0x40000000u;
    config->vm_arena_size = (uint32_t)vm_backing_size;
    config->vm_backing_bytes = vm_backing;
    config->vm_backing_byte_count = vm_backing_size;
    config->vm_existing_range_count = 3u;
    config->vm_existing_ranges[0].guest_base = VC_APF_RETAIL_TITLE_BASE;
    config->vm_existing_ranges[0].byte_count = VC_APF_RETAIL_TITLE_SIZE;
    config->vm_existing_ranges[0].kind = VC_APF_BOOT_VM_RANGE_TITLE_IMAGE;
    config->vm_existing_ranges[1].guest_base = VC_APF_STATIC_DISPATCH_BASE;
    config->vm_existing_ranges[1].byte_count = VC_APF_STATIC_DISPATCH_SIZE;
    config->vm_existing_ranges[1].kind =
        VC_APF_BOOT_VM_RANGE_STATIC_DISPATCH;
    config->vm_existing_ranges[2].guest_base =
        VC_APF_RETAIL_IMPORT_THUNK_BASE;
    config->vm_existing_ranges[2].byte_count =
        VC_APF_RETAIL_IMPORT_THUNK_SPAN;
    config->vm_existing_ranges[2].kind =
        VC_APF_BOOT_VM_RANGE_IMPORT_THUNKS;
}

static bool outside_seeded_slots_unchanged(const uint8_t *before,
                                           const uint8_t *after) {
    const size_t first =
        VC_APF_IMPORTED_DATA_XEX_SLOT - VC_APF_IMPORTED_DATA_IMAGE_BASE;
    const size_t second =
        VC_APF_IMPORTED_DATA_DEBUG_SLOT - VC_APF_IMPORTED_DATA_IMAGE_BASE;
    return memcmp(before, after, first) == 0 &&
           memcmp(before + first + 4u, after + first + 4u,
                  second - first - 4u) == 0 &&
           memcmp(before + second + 4u, after + second + 4u,
                  VC_APF_IMPORTED_DATA_IMAGE_SIZE - second - 4u) == 0;
}

int main(int argc, char **argv) {
    const size_t image_size = VC_APF_IMPORTED_DATA_IMAGE_SIZE;
    const size_t arena_size = VC_APF_IMPORTED_DATA_ARENA_ALIGNMENT;
    uint8_t *retail_image;
    uint8_t *image;
    uint8_t *image_snapshot;
    uint8_t *raw_xex;
    uint8_t *arena;
    uint8_t arena_snapshot[VC_APF_IMPORTED_DATA_ARENA_ALIGNMENT];
    uint8_t prefix_mutation[VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE];
    vc_apf_imported_data_config config;
    vc_apf_imported_data_result result;
    vc_apf_imported_data_result result_snapshot;
    vc_apf_imported_data_consumer_evidence evidence;
    vc_apf_boot_leaf_runtime *leaf_runtime;
    vc_apf_guest_thread leaf_thread;
    vc_apf_boot_leaf_config leaf_config;
    vc_apf_guest_memory xex_arena_memory;
    vc_apf_guest_ppc_context context;
    uint8_t *vm_backing;
    size_t index;

    CHECK(argc == 3);
    retail_image = read_exact_file(argv[1], image_size);
    image = (uint8_t *)malloc(image_size);
    image_snapshot = (uint8_t *)malloc(image_size);
    raw_xex = read_file_prefix(argv[2],
                               VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE);
    arena = (uint8_t *)calloc(1u, arena_size);
    leaf_runtime = (vc_apf_boot_leaf_runtime *)calloc(1u, sizeof(*leaf_runtime));
    vm_backing = (uint8_t *)calloc(1u, 0x00400000u);
    CHECK(retail_image != NULL && image != NULL && image_snapshot != NULL &&
          raw_xex != NULL && arena != NULL && leaf_runtime != NULL &&
          vm_backing != NULL);
    CHECK(memcmp(retail_image, "MZ", 2u) == 0);
    CHECK(memcmp(raw_xex, "XEX2", 4u) == 0);

    memset(&config, 0, sizeof(config));
    config.decoded_image_bytes = image;
    config.decoded_image_guest_base = VC_APF_IMPORTED_DATA_IMAGE_BASE;
    config.decoded_image_byte_count = image_size;
    config.raw_xex_prefix_bytes = raw_xex;
    config.raw_xex_prefix_byte_count =
        VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE;
    config.arena_bytes = arena;
    config.arena_guest_base = 0x81000000u;
    config.arena_byte_count = arena_size;
    config.debugger_enabled = false;

    /* Wrong full-image identity: no slot, arena, or result mutation. */
    memcpy(image, retail_image, image_size);
    image[0x1000u] ^= 1u;
    memcpy(image_snapshot, image, image_size);
    memcpy(arena_snapshot, arena, arena_size);
    memset(&result, 0xA5, sizeof(result));
    result_snapshot = result;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_WRONG_IMAGE);
    CHECK(memcmp(image, image_snapshot, image_size) == 0);
    CHECK(memcmp(arena, arena_snapshot, arena_size) == 0);
    CHECK(memcmp(&result, &result_snapshot, sizeof(result)) == 0);

    /* Wrong raw-XEX prefix: the same transactional guarantee holds. */
    memcpy(image, retail_image, image_size);
    memcpy(prefix_mutation, raw_xex, sizeof(prefix_mutation));
    prefix_mutation[sizeof(prefix_mutation) - 1u] ^= 1u;
    config.raw_xex_prefix_bytes = prefix_mutation;
    config.raw_xex_prefix_byte_count = sizeof(prefix_mutation);
    memcpy(image_snapshot, image, image_size);
    memset(&result, 0x5A, sizeof(result));
    result_snapshot = result;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_WRONG_XEX_PREFIX);
    CHECK(memcmp(image, image_snapshot, image_size) == 0);
    CHECK(memcmp(arena, arena_snapshot, arena_size) == 0);
    CHECK(memcmp(&result, &result_snapshot, sizeof(result)) == 0);
    config.raw_xex_prefix_bytes = raw_xex;
    config.raw_xex_prefix_byte_count =
        VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE;

    /* Explicit debugger, arena state, bounds, and overlap all fail closed. */
    config.debugger_enabled = true;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_UNSUPPORTED_CONFIGURATION);
    config.debugger_enabled = false;
    arena[0x20u] = 1u;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_ARENA_NOT_EMPTY);
    arena[0x20u] = 0u;
    config.arena_guest_base = VC_APF_IMPORTED_DATA_IMAGE_BASE;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_OVERLAP);
    config.arena_guest_base = 0x81000001u;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_BOUNDS);
    config.arena_guest_base = 0x81000000u;
    config.arena_byte_count = VC_APF_IMPORTED_DATA_ARENA_USED_SIZE - 1u;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_BOUNDS);
    config.arena_byte_count = arena_size;
    config.arena_bytes = image + 0x1000u;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_OVERLAP);
    config.arena_bytes = arena;
    config.raw_xex_prefix_bytes = image;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_OVERLAP);
    config.raw_xex_prefix_bytes = raw_xex;

    /* Successful one-shot seed. */
    memcpy(image, retail_image, image_size);
    memset(arena, 0, arena_size);
    memcpy(image_snapshot, image, image_size);
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_OK);
    CHECK(result.xex_export_cell == 0x81000000u);
    CHECK(result.executable_module_object == 0x81000010u);
    CHECK(result.debug_monitor_export_cell == 0x81000080u);
    CHECK(result.raw_xex_prefix == 0x81000100u);
    CHECK(result.seeded_slot_count == 2u);
    CHECK(result.preserved_ordinal_slot_count == 11u);
    CHECK(result.copied_xex_prefix_byte_count == 144u);
    CHECK(outside_seeded_slots_unchanged(image_snapshot, image));
    CHECK(load_be_u32(image +
                      (VC_APF_IMPORTED_DATA_XEX_SLOT -
                       VC_APF_IMPORTED_DATA_IMAGE_BASE)) ==
          result.xex_export_cell);
    CHECK(load_be_u32(image +
                      (VC_APF_IMPORTED_DATA_DEBUG_SLOT -
                       VC_APF_IMPORTED_DATA_IMAGE_BASE)) ==
          result.debug_monitor_export_cell);
    for (index = 0u; index < sizeof(imported_slots) /
                                   sizeof(imported_slots[0]);
         ++index) {
        const uint32_t address = imported_slots[index].address;
        if (address != VC_APF_IMPORTED_DATA_XEX_SLOT &&
            address != VC_APF_IMPORTED_DATA_DEBUG_SLOT) {
            CHECK(load_be_u32(image +
                              (address - VC_APF_IMPORTED_DATA_IMAGE_BASE)) ==
                  imported_slots[index].ordinal);
        }
    }
    CHECK(load_be_u32(arena + VC_APF_IMPORTED_DATA_XEX_CELL_OFFSET) ==
          result.executable_module_object);
    CHECK(load_be_u32(arena + VC_APF_IMPORTED_DATA_MODULE_OFFSET +
                      VC_APF_IMPORTED_DATA_MODULE_XEX_HEADER_OFFSET) ==
          result.raw_xex_prefix);
    CHECK(load_be_u32(arena + VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET) == 0u);
    CHECK(memcmp(arena + VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET, raw_xex,
                 VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE) == 0);
    CHECK(memcmp(image, "MZ", 2u) == 0);
    CHECK(memcmp(arena + VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET,
                 "XEX2", 4u) == 0);

    CHECK(vc_apf_imported_data_probe_consumers(&config, &result, &evidence) ==
          VC_APF_IMPORTED_DATA_OK);
    CHECK(evidence.sub_84bf1850_slot_load_address == 0x84BF186Cu);
    CHECK(evidence.rtl_image_xex_header_field_call_address == 0x84BF1888u);
    CHECK(evidence.requested_xex_key == 0x00020401u);
    CHECK(evidence.resolved_xex_header_address == result.raw_xex_prefix);
    CHECK(evidence.sub_84bf1850_reaches_header_query);
    CHECK(!evidence.requested_key_present);
    CHECK(evidence.bounded_absent_key_result_is_null);
    CHECK(evidence.sub_84bf1950_slot_load_address == 0x84BF196Cu);
    CHECK(evidence.sub_84bf1950_callback_call_address == 0x84BF198Cu);
    CHECK(evidence.resolved_debug_monitor_object == 0u);
    CHECK(evidence.debugger_disabled);
    CHECK(!evidence.callback_field_read);
    CHECK(!evidence.callback_dispatch_possible);

    /* Invoke the already-bounded absent DEFAULT_HEAP_SIZE leaf adapter. */
    configure_leaf_runtime(&leaf_config, vm_backing, 0x00400000u);
    CHECK(vc_apf_boot_leaf_runtime_init(leaf_runtime, &leaf_config) ==
          VC_APF_BOOT_LEAF_OK);
    vc_apf_boot_leaf_thread_init(&leaf_thread);
    CHECK(vc_apf_boot_leaf_thread_attach(leaf_runtime, &leaf_thread,
                                         0x90001000u) ==
          VC_APF_BOOT_LEAF_OK);
    memset(&context, 0, sizeof(context));
    context.lr = 0x84BF188Cu;
    context.gpr[3] = result.raw_xex_prefix;
    context.gpr[4] = VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE;
    xex_arena_memory.bytes = arena;
    xex_arena_memory.guest_base = config.arena_guest_base;
    xex_arena_memory.byte_count = config.arena_byte_count;
    CHECK(vc_apf_boot_leaf_dispatch(
              leaf_runtime, &leaf_thread, &xex_arena_memory, &context,
              VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);

    /* A second seed is rejected because the retail ordinal identity changed. */
    memcpy(image_snapshot, image, image_size);
    memcpy(arena_snapshot, arena, arena_size);
    result_snapshot = result;
    CHECK(vc_apf_imported_data_bootstrap(&config, &result) ==
          VC_APF_IMPORTED_DATA_WRONG_IMAGE);
    CHECK(memcmp(image, image_snapshot, image_size) == 0);
    CHECK(memcmp(arena, arena_snapshot, arena_size) == 0);
    CHECK(memcmp(&result, &result_snapshot, sizeof(result)) == 0);

    printf("APF_IMPORTED_DATA_BOOTSTRAP_PASS "
           "frontier_slots=2 preserved_ordinals=11 xex_prefix=144 "
           "header_query=yes default_heap_absent=yes debug_dispatch=no "
           "transactional=yes title_entry_called=no\n");

    free(vm_backing);
    free(leaf_runtime);
    free(arena);
    free(raw_xex);
    free(image_snapshot);
    free(image);
    free(retail_image);
    return 0;
}
