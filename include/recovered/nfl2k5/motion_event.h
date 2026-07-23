#ifndef VC_RECOVERED_NFL2K5_MOTION_EVENT_H
#define VC_RECOVERED_NFL2K5_MOTION_EVENT_H

#include <stdint.h>

typedef enum VcNflMotionEventStatus {
    VC_NFL_MOTION_EVENT_OK = 0,
    VC_NFL_MOTION_EVENT_END = 1,
    VC_NFL_MOTION_EVENT_BAD_ARGUMENT = 2,
    VC_NFL_MOTION_EVENT_BAD_TIME_SCALE = 3
} VcNflMotionEventStatus;

typedef struct VcNflMotionEvent {
    uint32_t raw_word;
    uint32_t tick;
    uint8_t event_id;
    float seconds;
} VcNflMotionEvent;

/* Portable record decode for NFL 2K5 default.xbe:0x000DF030. Event words are
   little-endian, low eight bits are an unnamed event ID, high 24 bits are
   1/65536-second ticks divided by the clip time scale, and 0xffffffff ends
   the stream. The destination is unchanged for END or an error. */
VcNflMotionEventStatus
vc_nfl_motion_event_decode_le(const uint8_t encoded[4],
                              float time_scale,
                              VcNflMotionEvent *event);

const char *vc_nfl_motion_event_status_name(VcNflMotionEventStatus status);

#endif
