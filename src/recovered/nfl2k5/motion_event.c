#include "recovered/nfl2k5/motion_event.h"

#include <math.h>
#include <stddef.h>

static uint32_t read_le32(const uint8_t encoded[4])
{
    return (uint32_t)encoded[0] |
           ((uint32_t)encoded[1] << 8) |
           ((uint32_t)encoded[2] << 16) |
           ((uint32_t)encoded[3] << 24);
}

VcNflMotionEventStatus
vc_nfl_motion_event_decode_le(const uint8_t encoded[4],
                              float time_scale,
                              VcNflMotionEvent *event)
{
    if (encoded == NULL || event == NULL) {
        return VC_NFL_MOTION_EVENT_BAD_ARGUMENT;
    }
    if (!isfinite(time_scale) || !(time_scale > 0.0f)) {
        return VC_NFL_MOTION_EVENT_BAD_TIME_SCALE;
    }
    const uint32_t word = read_le32(encoded);
    if (word == UINT32_MAX) {
        return VC_NFL_MOTION_EVENT_END;
    }
    const uint32_t tick = word >> 8;
    const VcNflMotionEvent decoded = {
        .raw_word = word,
        .tick = tick,
        .event_id = (uint8_t)(word & UINT32_C(0xFF)),
        .seconds = (float)tick * 0x1p-16f / time_scale,
    };
    *event = decoded;
    return VC_NFL_MOTION_EVENT_OK;
}

const char *vc_nfl_motion_event_status_name(VcNflMotionEventStatus status)
{
    switch (status) {
    case VC_NFL_MOTION_EVENT_OK: return "ok";
    case VC_NFL_MOTION_EVENT_END: return "end";
    case VC_NFL_MOTION_EVENT_BAD_ARGUMENT: return "bad-argument";
    case VC_NFL_MOTION_EVENT_BAD_TIME_SCALE: return "bad-time-scale";
    default: return "unknown";
    }
}
