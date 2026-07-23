#include "recovered/nfl2k5/motion_event.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "NFL motion event: %s\n", message);
        ++failures;
    }
}

static void event_test(void)
{
    static const uint8_t encoded[4] = {0x78, 0x56, 0x34, 0x12};
    VcNflMotionEvent event;
    expect_true(vc_nfl_motion_event_decode_le(encoded, 1.5f, &event) ==
                    VC_NFL_MOTION_EVENT_OK,
                "ordinary event did not decode");
    expect_true(event.raw_word == UINT32_C(0x12345678) &&
                    event.tick == UINT32_C(0x123456) &&
                    event.event_id == UINT8_C(0x78),
                "event word split differs");
    const float expected = (float)UINT32_C(0x123456) / 65536.0f / 1.5f;
    expect_true(isfinite(event.seconds) && event.seconds == expected,
                "event seconds conversion differs");
}

static void termination_and_failure_tests(void)
{
    static const uint8_t end[4] = {0xFF, 0xFF, 0xFF, 0xFF};
    VcNflMotionEvent event = {.raw_word = 7U};
    expect_true(vc_nfl_motion_event_decode_le(end, 1.0f, &event) ==
                    VC_NFL_MOTION_EVENT_END,
                "stream terminator was not recognized");
    expect_true(event.raw_word == 7U,
                "stream terminator modified destination");
    expect_true(vc_nfl_motion_event_decode_le(NULL, 1.0f, &event) ==
                    VC_NFL_MOTION_EVENT_BAD_ARGUMENT,
                "null event word was accepted");
    expect_true(vc_nfl_motion_event_decode_le(end, 0.0f, &event) ==
                    VC_NFL_MOTION_EVENT_BAD_TIME_SCALE,
                "zero time scale was accepted");
    expect_true(vc_nfl_motion_event_decode_le(end, NAN, &event) ==
                    VC_NFL_MOTION_EVENT_BAD_TIME_SCALE,
                "non-finite time scale was accepted");
    expect_true(strcmp(vc_nfl_motion_event_status_name(
                           VC_NFL_MOTION_EVENT_END),
                       "end") == 0,
                "status name mismatch");
}

int main(void)
{
    event_test();
    termination_and_failure_tests();
    if (failures != 0) {
        fprintf(stderr, "NFL_MOTION_EVENT_NATIVE_FAIL failures=%d\n", failures);
        return 1;
    }
    puts("NFL_MOTION_EVENT_NATIVE_PASS tick_bits=24 id_bits=8");
    return 0;
}
