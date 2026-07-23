#ifndef VC_RECOVERED_NFL2K5_QUATERNION_INTERPOLATION_H
#define VC_RECOVERED_NFL2K5_QUATERNION_INTERPOLATION_H

#include <stdbool.h>
#include <stdint.h>

typedef enum VcNflQuaternionInterpolationStatus {
    VC_NFL_QUATERNION_INTERPOLATION_OK = 0,
    VC_NFL_QUATERNION_INTERPOLATION_BAD_ARGUMENT = 1
} VcNflQuaternionInterpolationStatus;

typedef enum VcNflQuaternionInterpolationBranch {
    VC_NFL_QUATERNION_INTERPOLATION_LINEAR = 0,
    VC_NFL_QUATERNION_INTERPOLATION_FIXED_SLERP = 1
} VcNflQuaternionInterpolationBranch;

typedef struct VcNflQuaternionInterpolationInfo {
    VcNflQuaternionInterpolationBranch branch;
    bool shortest_path_negated;
    int32_t theta_units;
    int32_t step_units;
    float left_weight;
    float right_weight;
} VcNflQuaternionInterpolationInfo;

/* Portable, structurally faithful implementation of NFL 2K5
   default.xbe:0x003CA270. The four values deliberately remain numbered lanes:
   the engine's quaternion axis convention is not yet proved.

   The original uses a strict abs(dot)>0x1.ffe5cap-1f linear fallback. Its
   fixed branch quantizes acos to 65,536 units per turn, rounds theta*t away
   from zero, and evaluates the recovered 256-entry linear sine table. It does
   not normalize the output. Exact destination==left or destination==right
   aliasing is supported, matching the original's lane-at-a-time access.

   PORTME at 0x003CA275..0x003CA3C8: this implementation retains the original
   constants, table, and evaluation topology with ISO C long double. It cannot
   promise the original Xbox x87 control word, 80-bit register lifetime, or
   bit-identical spills on every Linux architecture. */
VcNflQuaternionInterpolationStatus
vc_nfl_quaternion_interpolate_portable(
    float destination[4],
    const float left[4],
    const float right[4],
    float t,
    VcNflQuaternionInterpolationInfo *info);

const char *vc_nfl_quaternion_interpolation_status_name(
    VcNflQuaternionInterpolationStatus status);

bool vc_nfl_quaternion_interpolation_is_xbox_x87_bit_exact(void);

#endif
