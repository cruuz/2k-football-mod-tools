#ifndef VC_RW_LINUX_H
#define VC_RW_LINUX_H

#include <stdbool.h>

/*
 * Research gate only. Neither supplied title has been proven to use
 * RenderWare, and NFL 2K5 has strong evidence for a proprietary Visual
 * Concepts renderer. Keep this header so a later verified RenderWare call
 * has an explicit Linux boundary, but do not manufacture fake bindings.
 */
typedef struct RwLinuxContext {
    bool verified_renderware_binary;
} RwLinuxContext;

static inline bool rw_linux_init(RwLinuxContext *context)
{
    if (context != NULL) {
        context->verified_renderware_binary = false;
    }
    /* PORTME: implement only after a valid RenderWare stream/API signature. */
    return false;
}

static inline void rw_linux_shutdown(RwLinuxContext *context)
{
    (void)context;
}

#endif

