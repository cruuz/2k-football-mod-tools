#ifndef VC_RECOVERED_NFL2K5_PLAYER_LOCAL_POSTPROCESS_H
#define VC_RECOVERED_NFL2K5_PLAYER_LOCAL_POSTPROCESS_H

#include "recovered/nfl2k5/player_current_postprocess.h"

#include <stddef.h>
#include <stdint.h>

#define VC_NFL_PLAYER_92140_OPERATION_COUNT 127u
#define VC_NFL_PLAYER_ANGLE_LUT_FLOAT_COUNT 512u
#define VC_NFL_PLAYER_ANGLE_COEFFICIENT_COUNT 6u
#define VC_NFL_PLAYER_LOCAL_CONSTANT_FLOAT_COUNT 351u

typedef enum VcNflPlayerLocalPostprocessStatus {
    VC_NFL_PLAYER_LOCAL_POSTPROCESS_OK = 0,
    VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_ARGUMENT = 1,
    VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_TABLES = 2
} VcNflPlayerLocalPostprocessStatus;

typedef struct VcNflPlayerLocalPostprocessTables {
    uint8_t low_to_high[VC_NFL_PLAYER_LOW_MATRIX_COUNT];
    float angle_lut[VC_NFL_PLAYER_ANGLE_LUT_FLOAT_COUNT];
    float angle_coefficients[VC_NFL_PLAYER_ANGLE_COEFFICIENT_COUNT];
    float projection_lower_clamp;
    float angle_scale;
    float blend_scale;
    float local_constants[VC_NFL_PLAYER_LOCAL_CONSTANT_FLOAT_COUNT];
} VcNflPlayerLocalPostprocessTables;

typedef struct VcNflPlayerLocalMatrices {
    float low[VC_NFL_PLAYER_LOW_MATRIX_COUNT][16];
    float high[VC_NFL_PLAYER_HIGH_MATRIX_COUNT][16];
} VcNflPlayerLocalMatrices;

typedef void (*VcNflPlayer92140TraceCallback)(
    void *user_data, uint32_t sequence, uint32_t xbe_callsite);

/* Portable, bounded translation of NFL 2K5 US default.xbe 0x00092140.

   skeleton_vectors is the exact 25-record SKEL table in LO_res order.  The
   table object deliberately remains caller supplied: the strict validator
   obtains every float from the pinned XBE and compares this implementation
   against a separately implemented ordered-graph oracle.

   Every argument/table check completes before matrices is changed.  On
   success, all 62 high matrices receive a writer.  The optional observer is
   called once for each of the original function's 127 helper calls, in
   address order; it is diagnostic and must not mutate inputs or outputs.

   PORTME(0x0008D630): normalization uses sqrtf rather than the Xbox SSE
   rsqrt seed plus one Newton refinement, so arbitrary-input bit identity is
   not claimed.
   PORTME(0x00020B20/0x0008D550): C truncation is value-equivalent for the
   finite shipped-domain values; exact exceptional x87/SSE conversion flags
   are not modeled.
   PORTME(0x00091D90/0x00091E70/0x00091F60): the original global scratch is
   intentionally replaced with stack-local matrices to make this port
   reentrant; no ordering-visible persistent side effect is omitted. */
VcNflPlayerLocalPostprocessStatus vc_nfl_player_local_postprocess_92140(
    const float skeleton_vectors[VC_NFL_PLAYER_LOW_MATRIX_COUNT][4],
    const VcNflPlayerLocalPostprocessTables *tables,
    VcNflPlayerLocalMatrices *matrices,
    VcNflPlayer92140TraceCallback observer,
    void *observer_user_data);

const char *vc_nfl_player_local_postprocess_status_name(
    VcNflPlayerLocalPostprocessStatus status);

const char *vc_nfl_player_low_matrix_name(size_t index);
const char *vc_nfl_player_high_matrix_name(size_t index);

#endif
