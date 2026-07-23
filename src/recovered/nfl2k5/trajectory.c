#include "recovered/nfl2k5/trajectory.h"

#include <string.h>

static int16_t read_le_i16(const uint8_t encoded[2])
{
    const uint16_t raw = (uint16_t)encoded[0] |
                         (uint16_t)((uint16_t)encoded[1] << 8);
    int16_t value = 0;
    memcpy(&value, &raw, sizeof(value));
    return value;
}

static float flip_float_sign(float value)
{
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    bits ^= UINT32_C(0x80000000);
    memcpy(&value, &bits, sizeof(value));
    return value;
}

VcNflTrajectoryStatus
vc_nfl_trajectory_decode_record_le(const uint8_t *encoded,
                                   size_t stride,
                                   VcNflTrajectorySample *sample)
{
    if (encoded == NULL || sample == NULL) {
        return VC_NFL_TRAJECTORY_BAD_ARGUMENT;
    }
    if (stride != 6U && stride != 8U) {
        return VC_NFL_TRAJECTORY_BAD_STRIDE;
    }

    const int16_t packed[4] = {
        read_le_i16(encoded),
        read_le_i16(encoded + 2),
        read_le_i16(encoded + 4),
        stride == 8U ? read_le_i16(encoded + 6) : 0,
    };
    VcNflTrajectorySample decoded = {
        .lanes = {
            (float)packed[0] * 0.125f,
            (float)packed[1] * 0.125f,
            (float)packed[2] * 0.125f,
        },
        .packed_lanes = {packed[0], packed[1], packed[2], packed[3]},
        .yaw_like = stride == 8U ? (int32_t)packed[3] * 8 : 0,
        .has_yaw_like = stride == 8U,
    };
    *sample = decoded;
    return VC_NFL_TRAJECTORY_OK;
}

VcNflTrajectoryStatus
vc_nfl_trajectory_decode_many_le(const uint8_t *encoded,
                                 size_t stride,
                                 size_t sample_count,
                                 VcNflTrajectorySample *samples,
                                 size_t *failed_index)
{
    if (encoded == NULL || samples == NULL) {
        return VC_NFL_TRAJECTORY_BAD_ARGUMENT;
    }
    if (stride != 6U && stride != 8U) {
        return VC_NFL_TRAJECTORY_BAD_STRIDE;
    }
    for (size_t index = 0; index < sample_count; ++index) {
        const VcNflTrajectoryStatus status =
            vc_nfl_trajectory_decode_record_le(encoded + index * stride,
                                               stride, &samples[index]);
        if (status != VC_NFL_TRAJECTORY_OK) {
            if (failed_index != NULL) {
                *failed_index = index;
            }
            return status;
        }
    }
    return VC_NFL_TRAJECTORY_OK;
}

void vc_nfl_trajectory_apply_mirror(VcNflTrajectorySample *sample)
{
    if (sample == NULL) {
        return;
    }
    sample->lanes[0] = flip_float_sign(sample->lanes[0]);
    sample->yaw_like = -sample->yaw_like;
}

const char *vc_nfl_trajectory_status_name(VcNflTrajectoryStatus status)
{
    switch (status) {
    case VC_NFL_TRAJECTORY_OK: return "ok";
    case VC_NFL_TRAJECTORY_BAD_ARGUMENT: return "bad-argument";
    case VC_NFL_TRAJECTORY_BAD_STRIDE: return "bad-stride";
    default: return "unknown";
    }
}
