#include "recovered/nfl2k5/packed_pose.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

static uint32_t read_le32(const uint8_t encoded[4])
{
    return (uint32_t)encoded[0] |
           ((uint32_t)encoded[1] << 8) |
           ((uint32_t)encoded[2] << 16) |
           ((uint32_t)encoded[3] << 24);
}

static float flip_float_sign(float value)
{
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    bits ^= UINT32_C(0x80000000);
    memcpy(&value, &bits, sizeof(value));
    return value;
}

VcNflPackedPoseStatus
vc_nfl_packed_pose_decode_le_portable(const uint8_t encoded[4],
                                      VcNflPackedPose *pose)
{
    if (encoded == NULL || pose == NULL) {
        return VC_NFL_PACKED_POSE_BAD_ARGUMENT;
    }

    const uint32_t word = read_le32(encoded);
    const int16_t packed[3] = {
        (int16_t)((int32_t)((word >> 20) & UINT32_C(0x3FF)) - 512),
        (int16_t)((int32_t)((word >> 10) & UINT32_C(0x3FF)) - 512),
        (int16_t)((int32_t)(word & UINT32_C(0x3FF)) - 512),
    };
    /* Exact f32 bits 0x3AB55FA3 from default.xbe:0x004EEA18. */
    const float scale = 0x1.6abf46p-10f;
    const float stored[3] = {
        (float)packed[0] * scale,
        (float)packed[1] * scale,
        (float)packed[2] * scale,
    };
    const float radicand =
        1.0f - (stored[0] * stored[0] + stored[1] * stored[1] +
                stored[2] * stored[2]);
    if (!(radicand >= 0.0f) || !isfinite(radicand)) {
        return VC_NFL_PACKED_POSE_NEGATIVE_RADICAND;
    }

    VcNflPackedPose decoded = {
        .packed_components = {packed[0], packed[1], packed[2]},
        .ideal_radicand = radicand,
        .omitted_component = (uint8_t)(word >> 30),
    };
    const float missing = sqrtf(radicand);
    size_t stored_index = 0;
    for (size_t lane = 0; lane < 4; ++lane) {
        if (lane == (size_t)decoded.omitted_component) {
            decoded.lanes[lane] = missing;
        } else {
            decoded.lanes[lane] = stored[stored_index];
            ++stored_index;
        }
    }
    *pose = decoded;
    return VC_NFL_PACKED_POSE_OK;
}

VcNflPackedPoseStatus
vc_nfl_packed_pose_decode_many_le_portable(const uint8_t *encoded,
                                           size_t pose_count,
                                           VcNflPackedPose *poses,
                                           size_t *failed_index)
{
    if (encoded == NULL || poses == NULL) {
        return VC_NFL_PACKED_POSE_BAD_ARGUMENT;
    }
    for (size_t index = 0; index < pose_count; ++index) {
        const VcNflPackedPoseStatus status =
            vc_nfl_packed_pose_decode_le_portable(encoded + index * 4U,
                                                   &poses[index]);
        if (status != VC_NFL_PACKED_POSE_OK) {
            if (failed_index != NULL) {
                *failed_index = index;
            }
            return status;
        }
    }
    return VC_NFL_PACKED_POSE_OK;
}

void vc_nfl_packed_pose_apply_mirror(VcNflPackedPose *pose)
{
    if (pose == NULL) {
        return;
    }
    pose->lanes[2] = flip_float_sign(pose->lanes[2]);
    pose->lanes[3] = flip_float_sign(pose->lanes[3]);
}

const char *vc_nfl_packed_pose_status_name(VcNflPackedPoseStatus status)
{
    switch (status) {
    case VC_NFL_PACKED_POSE_OK: return "ok";
    case VC_NFL_PACKED_POSE_BAD_ARGUMENT: return "bad-argument";
    case VC_NFL_PACKED_POSE_NEGATIVE_RADICAND: return "negative-radicand";
    default: return "unknown";
    }
}

bool vc_nfl_packed_pose_decoder_is_xbox_x87_bit_exact(void)
{
    return false;
}
