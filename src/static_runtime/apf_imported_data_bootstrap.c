#include "static_runtime/apf_imported_data_bootstrap.h"

#include <limits.h>
#include <string.h>

typedef struct vc_apf_sha256 {
    uint32_t state[8];
    uint64_t bit_count;
    uint8_t block[64];
    size_t block_size;
} vc_apf_sha256;

typedef struct vc_apf_imported_slot_signature {
    uint32_t address;
    uint32_t ordinal_word;
} vc_apf_imported_slot_signature;

static const vc_apf_imported_slot_signature vc_apf_imported_slots[] = {
    {0x82000744u, 0x000101AEu}, {0x820007ACu, 0x00010193u},
    {0x820007CCu, 0x000100ADu}, {0x8200080Cu, 0x0001001Cu},
    {0x8200081Cu, 0x00010017u}, {0x82000828u, 0x0001000Eu},
    {0x82000870u, 0x000101C1u}, {0x82000888u, 0x000101C0u},
    {0x820008BCu, 0x00010158u}, {0x820008D8u, 0x0001001Bu},
    {0x82000938u, 0x000101BEu}, {0x8200093Cu, 0x00010266u},
    {0x82000940u, 0x00010059u},
};

static const uint8_t vc_apf_decoded_image_sha256[32] = {
    0xCDu, 0xE5u, 0xB9u, 0x22u, 0x4Cu, 0x6Fu, 0x99u, 0x90u,
    0x60u, 0xDFu, 0x73u, 0x72u, 0xEEu, 0xA1u, 0xBFu, 0xD6u,
    0x46u, 0x3Du, 0x63u, 0xB4u, 0xE5u, 0x9Au, 0x87u, 0xB2u,
    0x80u, 0x18u, 0x26u, 0xF7u, 0x6Du, 0x52u, 0xB1u, 0xCFu,
};

static const uint8_t vc_apf_raw_xex_prefix_sha256[32] = {
    0x1Au, 0x5Au, 0xCDu, 0xCFu, 0xDFu, 0x3Au, 0x0Bu, 0x86u,
    0x9Au, 0x44u, 0xB3u, 0x0Fu, 0xDDu, 0x1Au, 0x25u, 0xFAu,
    0x1Eu, 0xD4u, 0x5Au, 0x21u, 0xDBu, 0xD7u, 0xB6u, 0x29u,
    0x2Fu, 0x6Bu, 0x81u, 0xDBu, 0x1Bu, 0x1Au, 0x79u, 0x60u,
};

static const uint32_t vc_apf_sha256_constants[64] = {
    0x428A2F98u, 0x71374491u, 0xB5C0FBCFu, 0xE9B5DBA5u,
    0x3956C25Bu, 0x59F111F1u, 0x923F82A4u, 0xAB1C5ED5u,
    0xD807AA98u, 0x12835B01u, 0x243185BEu, 0x550C7DC3u,
    0x72BE5D74u, 0x80DEB1FEu, 0x9BDC06A7u, 0xC19BF174u,
    0xE49B69C1u, 0xEFBE4786u, 0x0FC19DC6u, 0x240CA1CCu,
    0x2DE92C6Fu, 0x4A7484AAu, 0x5CB0A9DCu, 0x76F988DAu,
    0x983E5152u, 0xA831C66Du, 0xB00327C8u, 0xBF597FC7u,
    0xC6E00BF3u, 0xD5A79147u, 0x06CA6351u, 0x14292967u,
    0x27B70A85u, 0x2E1B2138u, 0x4D2C6DFCu, 0x53380D13u,
    0x650A7354u, 0x766A0ABBu, 0x81C2C92Eu, 0x92722C85u,
    0xA2BFE8A1u, 0xA81A664Bu, 0xC24B8B70u, 0xC76C51A3u,
    0xD192E819u, 0xD6990624u, 0xF40E3585u, 0x106AA070u,
    0x19A4C116u, 0x1E376C08u, 0x2748774Cu, 0x34B0BCB5u,
    0x391C0CB3u, 0x4ED8AA4Au, 0x5B9CCA4Fu, 0x682E6FF3u,
    0x748F82EEu, 0x78A5636Fu, 0x84C87814u, 0x8CC70208u,
    0x90BEFFFAu, 0xA4506CEBu, 0xBEF9A3F7u, 0xC67178F2u,
};

_Static_assert(sizeof(vc_apf_imported_slots) /
                       sizeof(vc_apf_imported_slots[0]) == 13u,
               "APF imported-data signature count changed");
_Static_assert(VC_APF_IMPORTED_DATA_XEX_CELL_OFFSET + 4u <=
                   VC_APF_IMPORTED_DATA_MODULE_OFFSET,
               "APF imported-data arena objects overlap");
_Static_assert(VC_APF_IMPORTED_DATA_MODULE_OFFSET +
                       VC_APF_IMPORTED_DATA_MODULE_SIZE <=
                   VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET,
               "APF imported-data arena objects overlap");
_Static_assert(VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET + 4u <=
                   VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET,
               "APF imported-data arena objects overlap");
_Static_assert(VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET +
                       VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE ==
                   VC_APF_IMPORTED_DATA_ARENA_USED_SIZE,
               "APF imported-data arena size changed");

static uint32_t vc_apf_rotr32(uint32_t value, unsigned int count) {
    return (value >> count) | (value << (32u - count));
}

static uint32_t vc_apf_load_be_u32(const uint8_t *bytes) {
    return ((uint32_t)bytes[0] << 24u) | ((uint32_t)bytes[1] << 16u) |
           ((uint32_t)bytes[2] << 8u) | (uint32_t)bytes[3];
}

static void vc_apf_store_be_u32(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)(value >> 24u);
    bytes[1] = (uint8_t)(value >> 16u);
    bytes[2] = (uint8_t)(value >> 8u);
    bytes[3] = (uint8_t)value;
}

static void vc_apf_sha256_transform(vc_apf_sha256 *context,
                                    const uint8_t block[64]) {
    uint32_t words[64];
    uint32_t a;
    uint32_t b;
    uint32_t c;
    uint32_t d;
    uint32_t e;
    uint32_t f;
    uint32_t g;
    uint32_t h;
    size_t index;

    for (index = 0u; index < 16u; ++index) {
        words[index] = vc_apf_load_be_u32(block + index * 4u);
    }
    for (index = 16u; index < 64u; ++index) {
        const uint32_t s0 = vc_apf_rotr32(words[index - 15u], 7u) ^
                            vc_apf_rotr32(words[index - 15u], 18u) ^
                            (words[index - 15u] >> 3u);
        const uint32_t s1 = vc_apf_rotr32(words[index - 2u], 17u) ^
                            vc_apf_rotr32(words[index - 2u], 19u) ^
                            (words[index - 2u] >> 10u);
        words[index] = words[index - 16u] + s0 + words[index - 7u] + s1;
    }

    a = context->state[0];
    b = context->state[1];
    c = context->state[2];
    d = context->state[3];
    e = context->state[4];
    f = context->state[5];
    g = context->state[6];
    h = context->state[7];
    for (index = 0u; index < 64u; ++index) {
        const uint32_t sum1 = vc_apf_rotr32(e, 6u) ^
                              vc_apf_rotr32(e, 11u) ^
                              vc_apf_rotr32(e, 25u);
        const uint32_t choose = (e & f) ^ ((~e) & g);
        const uint32_t temp1 = h + sum1 + choose +
                               vc_apf_sha256_constants[index] + words[index];
        const uint32_t sum0 = vc_apf_rotr32(a, 2u) ^
                              vc_apf_rotr32(a, 13u) ^
                              vc_apf_rotr32(a, 22u);
        const uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        const uint32_t temp2 = sum0 + majority;
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }
    context->state[0] += a;
    context->state[1] += b;
    context->state[2] += c;
    context->state[3] += d;
    context->state[4] += e;
    context->state[5] += f;
    context->state[6] += g;
    context->state[7] += h;
}

static void vc_apf_sha256_init(vc_apf_sha256 *context) {
    static const uint32_t initial[8] = {
        0x6A09E667u, 0xBB67AE85u, 0x3C6EF372u, 0xA54FF53Au,
        0x510E527Fu, 0x9B05688Cu, 0x1F83D9ABu, 0x5BE0CD19u,
    };
    memcpy(context->state, initial, sizeof(initial));
    context->bit_count = 0u;
    context->block_size = 0u;
}

static void vc_apf_sha256_update(vc_apf_sha256 *context,
                                 const uint8_t *bytes,
                                 size_t byte_count) {
    size_t offset = 0u;
    while (offset < byte_count) {
        size_t copy_count = 64u - context->block_size;
        if (copy_count > byte_count - offset) {
            copy_count = byte_count - offset;
        }
        memcpy(context->block + context->block_size, bytes + offset,
               copy_count);
        context->block_size += copy_count;
        offset += copy_count;
        if (context->block_size == 64u) {
            vc_apf_sha256_transform(context, context->block);
            context->bit_count += 512u;
            context->block_size = 0u;
        }
    }
}

static void vc_apf_sha256_final(vc_apf_sha256 *context, uint8_t digest[32]) {
    uint64_t total_bits = context->bit_count + context->block_size * 8u;
    size_t index;

    context->block[context->block_size++] = 0x80u;
    if (context->block_size > 56u) {
        memset(context->block + context->block_size, 0,
               64u - context->block_size);
        vc_apf_sha256_transform(context, context->block);
        context->block_size = 0u;
    }
    memset(context->block + context->block_size, 0,
           56u - context->block_size);
    for (index = 0u; index < 8u; ++index) {
        context->block[63u - index] = (uint8_t)(total_bits >> (index * 8u));
    }
    vc_apf_sha256_transform(context, context->block);
    for (index = 0u; index < 8u; ++index) {
        vc_apf_store_be_u32(digest + index * 4u, context->state[index]);
    }
}

static bool vc_apf_sha256_matches(const uint8_t *bytes, size_t byte_count,
                                  const uint8_t expected[32]) {
    vc_apf_sha256 context;
    uint8_t actual[32];
    vc_apf_sha256_init(&context);
    vc_apf_sha256_update(&context, bytes, byte_count);
    vc_apf_sha256_final(&context, actual);
    return memcmp(actual, expected, sizeof(actual)) == 0;
}

static bool vc_apf_host_ranges_overlap(const void *left, size_t left_size,
                                       const void *right, size_t right_size) {
    const uintptr_t left_begin = (uintptr_t)left;
    const uintptr_t right_begin = (uintptr_t)right;
    uintptr_t left_end;
    uintptr_t right_end;
    if (left_size > UINTPTR_MAX - left_begin ||
        right_size > UINTPTR_MAX - right_begin) {
        return true;
    }
    left_end = left_begin + left_size;
    right_end = right_begin + right_size;
    return left_begin < right_end && right_begin < left_end;
}

static bool vc_apf_guest_ranges_overlap(uint32_t left, size_t left_size,
                                        uint32_t right, size_t right_size) {
    const uint64_t left_end = (uint64_t)left + left_size;
    const uint64_t right_end = (uint64_t)right + right_size;
    return (uint64_t)left < right_end && (uint64_t)right < left_end;
}

static bool vc_apf_arena_used_bytes_are_zero(const uint8_t *arena) {
    size_t index;
    for (index = 0u; index < VC_APF_IMPORTED_DATA_ARENA_USED_SIZE; ++index) {
        if (arena[index] != 0u) {
            return false;
        }
    }
    return true;
}

static bool vc_apf_xex_prefix_has_default_heap_size(const uint8_t *prefix) {
    size_t index;
    for (index = 0u; index < 15u; ++index) {
        if (vc_apf_load_be_u32(prefix + 24u + index * 8u) ==
            VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE) {
            return true;
        }
    }
    return false;
}

vc_apf_imported_data_status vc_apf_imported_data_bootstrap(
    const vc_apf_imported_data_config *config,
    vc_apf_imported_data_result *result) {
    vc_apf_imported_data_result local_result;
    uint64_t arena_end;
    size_t slot_index;

    if (config == NULL || result == NULL ||
        config->decoded_image_bytes == NULL ||
        config->raw_xex_prefix_bytes == NULL || config->arena_bytes == NULL) {
        return VC_APF_IMPORTED_DATA_INVALID_ARGUMENT;
    }
    if (config->debugger_enabled) {
        return VC_APF_IMPORTED_DATA_UNSUPPORTED_CONFIGURATION;
    }
    if (config->decoded_image_guest_base !=
            VC_APF_IMPORTED_DATA_IMAGE_BASE ||
        config->decoded_image_byte_count !=
            VC_APF_IMPORTED_DATA_IMAGE_SIZE) {
        return VC_APF_IMPORTED_DATA_WRONG_IMAGE;
    }
    if (config->raw_xex_prefix_byte_count <
            VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE) {
        return VC_APF_IMPORTED_DATA_WRONG_XEX_PREFIX;
    }
    if (config->arena_byte_count < VC_APF_IMPORTED_DATA_ARENA_USED_SIZE ||
        (config->arena_guest_base &
         (VC_APF_IMPORTED_DATA_ARENA_ALIGNMENT - 1u)) != 0u) {
        return VC_APF_IMPORTED_DATA_BOUNDS;
    }
    arena_end = (uint64_t)config->arena_guest_base + config->arena_byte_count;
    if (arena_end > UINT64_C(0x100000000)) {
        return VC_APF_IMPORTED_DATA_BOUNDS;
    }
    if (vc_apf_guest_ranges_overlap(
            config->arena_guest_base, config->arena_byte_count,
            VC_APF_IMPORTED_DATA_IMAGE_BASE,
            VC_APF_IMPORTED_DATA_IMAGE_SIZE) ||
        vc_apf_guest_ranges_overlap(
            config->arena_guest_base, config->arena_byte_count,
            VC_APF_IMPORTED_DATA_DISPATCH_BASE,
            VC_APF_IMPORTED_DATA_DISPATCH_SIZE) ||
        vc_apf_host_ranges_overlap(
            config->decoded_image_bytes, config->decoded_image_byte_count,
            config->arena_bytes, config->arena_byte_count) ||
        vc_apf_host_ranges_overlap(
            config->decoded_image_bytes, config->decoded_image_byte_count,
            config->raw_xex_prefix_bytes,
            VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE) ||
        vc_apf_host_ranges_overlap(
            config->raw_xex_prefix_bytes,
            VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE,
            config->arena_bytes, config->arena_byte_count)) {
        return VC_APF_IMPORTED_DATA_OVERLAP;
    }
    if (!vc_apf_sha256_matches(config->decoded_image_bytes,
                               config->decoded_image_byte_count,
                               vc_apf_decoded_image_sha256)) {
        return VC_APF_IMPORTED_DATA_WRONG_IMAGE;
    }
    if (!vc_apf_sha256_matches(config->raw_xex_prefix_bytes,
                               VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE,
                               vc_apf_raw_xex_prefix_sha256)) {
        return VC_APF_IMPORTED_DATA_WRONG_XEX_PREFIX;
    }
    for (slot_index = 0u;
         slot_index < sizeof(vc_apf_imported_slots) /
                          sizeof(vc_apf_imported_slots[0]);
         ++slot_index) {
        const size_t offset =
            vc_apf_imported_slots[slot_index].address -
            VC_APF_IMPORTED_DATA_IMAGE_BASE;
        if (offset > config->decoded_image_byte_count - 4u ||
            vc_apf_load_be_u32(config->decoded_image_bytes + offset) !=
                vc_apf_imported_slots[slot_index].ordinal_word) {
            return VC_APF_IMPORTED_DATA_WRONG_IMAGE;
        }
    }
    if (!vc_apf_arena_used_bytes_are_zero(config->arena_bytes)) {
        return VC_APF_IMPORTED_DATA_ARENA_NOT_EMPTY;
    }

    /* All validation is complete. The bounded writes below cannot fail. */
    memset(&local_result, 0, sizeof(local_result));
    local_result.xex_export_cell =
        config->arena_guest_base + VC_APF_IMPORTED_DATA_XEX_CELL_OFFSET;
    local_result.executable_module_object =
        config->arena_guest_base + VC_APF_IMPORTED_DATA_MODULE_OFFSET;
    local_result.debug_monitor_export_cell =
        config->arena_guest_base + VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET;
    local_result.raw_xex_prefix =
        config->arena_guest_base + VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET;
    local_result.seeded_slot_count = 2u;
    local_result.preserved_ordinal_slot_count = 11u;
    local_result.copied_xex_prefix_byte_count =
        VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE;

    memcpy(config->arena_bytes + VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET,
           config->raw_xex_prefix_bytes,
           VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE);
    vc_apf_store_be_u32(
        config->arena_bytes + VC_APF_IMPORTED_DATA_XEX_CELL_OFFSET,
        local_result.executable_module_object);
    vc_apf_store_be_u32(
        config->arena_bytes + VC_APF_IMPORTED_DATA_MODULE_OFFSET +
            VC_APF_IMPORTED_DATA_MODULE_XEX_HEADER_OFFSET,
        local_result.raw_xex_prefix);
    vc_apf_store_be_u32(
        config->arena_bytes + VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET, 0u);
    vc_apf_store_be_u32(
        config->decoded_image_bytes +
            (VC_APF_IMPORTED_DATA_XEX_SLOT -
             VC_APF_IMPORTED_DATA_IMAGE_BASE),
        local_result.xex_export_cell);
    vc_apf_store_be_u32(
        config->decoded_image_bytes +
            (VC_APF_IMPORTED_DATA_DEBUG_SLOT -
             VC_APF_IMPORTED_DATA_IMAGE_BASE),
        local_result.debug_monitor_export_cell);
    *result = local_result;
    return VC_APF_IMPORTED_DATA_OK;
}

vc_apf_imported_data_status vc_apf_imported_data_probe_consumers(
    const vc_apf_imported_data_config *config,
    const vc_apf_imported_data_result *result,
    vc_apf_imported_data_consumer_evidence *evidence) {
    vc_apf_imported_data_consumer_evidence local;
    uint32_t xex_cell;
    uint32_t module;
    uint32_t header;
    uint32_t debug_cell;
    uint32_t debug_object;

    if (config == NULL || result == NULL || evidence == NULL ||
        config->decoded_image_bytes == NULL || config->arena_bytes == NULL ||
        config->decoded_image_guest_base != VC_APF_IMPORTED_DATA_IMAGE_BASE ||
        config->decoded_image_byte_count != VC_APF_IMPORTED_DATA_IMAGE_SIZE ||
        config->arena_byte_count < VC_APF_IMPORTED_DATA_ARENA_USED_SIZE) {
        return VC_APF_IMPORTED_DATA_INVALID_ARGUMENT;
    }
    xex_cell = vc_apf_load_be_u32(
        config->decoded_image_bytes +
        (VC_APF_IMPORTED_DATA_XEX_SLOT - VC_APF_IMPORTED_DATA_IMAGE_BASE));
    if (xex_cell != result->xex_export_cell ||
        xex_cell != config->arena_guest_base +
                        VC_APF_IMPORTED_DATA_XEX_CELL_OFFSET) {
        return VC_APF_IMPORTED_DATA_GUEST_STATE;
    }
    module = vc_apf_load_be_u32(
        config->arena_bytes + VC_APF_IMPORTED_DATA_XEX_CELL_OFFSET);
    if (module != result->executable_module_object ||
        module != config->arena_guest_base +
                      VC_APF_IMPORTED_DATA_MODULE_OFFSET) {
        return VC_APF_IMPORTED_DATA_GUEST_STATE;
    }
    header = vc_apf_load_be_u32(
        config->arena_bytes + VC_APF_IMPORTED_DATA_MODULE_OFFSET +
        VC_APF_IMPORTED_DATA_MODULE_XEX_HEADER_OFFSET);
    if (header != result->raw_xex_prefix ||
        header != config->arena_guest_base +
                      VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET ||
        !vc_apf_sha256_matches(
            config->arena_bytes + VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET,
            VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE,
            vc_apf_raw_xex_prefix_sha256)) {
        return VC_APF_IMPORTED_DATA_GUEST_STATE;
    }
    debug_cell = vc_apf_load_be_u32(
        config->decoded_image_bytes +
        (VC_APF_IMPORTED_DATA_DEBUG_SLOT - VC_APF_IMPORTED_DATA_IMAGE_BASE));
    if (debug_cell != result->debug_monitor_export_cell ||
        debug_cell != config->arena_guest_base +
                          VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET) {
        return VC_APF_IMPORTED_DATA_GUEST_STATE;
    }
    debug_object = vc_apf_load_be_u32(
        config->arena_bytes + VC_APF_IMPORTED_DATA_DEBUG_CELL_OFFSET);
    if (debug_object != 0u || config->debugger_enabled) {
        return VC_APF_IMPORTED_DATA_GUEST_STATE;
    }

    memset(&local, 0, sizeof(local));
    local.sub_84bf1850_slot_load_address = 0x84BF186Cu;
    local.sub_84bf1850_header_load_address = 0x84BF1880u;
    local.rtl_image_xex_header_field_call_address = 0x84BF1888u;
    local.rtl_image_xex_header_field_return_address = 0x84BF188Cu;
    local.requested_xex_key = VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE;
    local.resolved_xex_header_address = header;
    local.sub_84bf1850_reaches_header_query = true;
    local.requested_key_present = vc_apf_xex_prefix_has_default_heap_size(
        config->arena_bytes + VC_APF_IMPORTED_DATA_XEX_PREFIX_OFFSET);
    local.bounded_absent_key_result_is_null = !local.requested_key_present;
    local.sub_84bf1950_slot_load_address = 0x84BF196Cu;
    local.sub_84bf1950_callback_call_address = 0x84BF198Cu;
    local.resolved_debug_monitor_object = debug_object;
    local.debugger_disabled = true;
    local.callback_field_read = false;
    local.callback_dispatch_possible = false;
    *evidence = local;
    return VC_APF_IMPORTED_DATA_OK;
}

const char *vc_apf_imported_data_status_name(
    vc_apf_imported_data_status status) {
    switch (status) {
        case VC_APF_IMPORTED_DATA_OK:
            return "ok";
        case VC_APF_IMPORTED_DATA_INVALID_ARGUMENT:
            return "invalid_argument";
        case VC_APF_IMPORTED_DATA_UNSUPPORTED_CONFIGURATION:
            return "unsupported_configuration";
        case VC_APF_IMPORTED_DATA_WRONG_IMAGE:
            return "wrong_image";
        case VC_APF_IMPORTED_DATA_WRONG_XEX_PREFIX:
            return "wrong_xex_prefix";
        case VC_APF_IMPORTED_DATA_BOUNDS:
            return "bounds";
        case VC_APF_IMPORTED_DATA_OVERLAP:
            return "overlap";
        case VC_APF_IMPORTED_DATA_ARENA_NOT_EMPTY:
            return "arena_not_empty";
        case VC_APF_IMPORTED_DATA_GUEST_STATE:
            return "guest_state";
        default:
            return "unknown";
    }
}
