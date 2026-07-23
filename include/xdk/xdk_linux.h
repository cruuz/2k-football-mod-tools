#ifndef VC_XDK_LINUX_H
#define VC_XDK_LINUX_H

#include <SDL2/SDL.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

typedef struct VcXInputState {
    uint32_t packet_number;
    uint16_t buttons;
    uint8_t left_trigger;
    uint8_t right_trigger;
    int16_t thumb_lx;
    int16_t thumb_ly;
    int16_t thumb_rx;
    int16_t thumb_ry;
} VcXInputState;

typedef int (*VcThreadFunction)(void *context);

/* Host adapters used by the research shell, not ABI-compatible XDK exports.
 * PORTME: add recovered title-specific error codes, path semantics, async I/O,
 * controller vibration, audio voices, synchronization, and thread affinity
 * only as their call sites and data layouts are validated. */
bool vc_xdk_init(void);
void vc_xdk_shutdown(void);
void vc_xdk_handle_event(const SDL_Event *event);
int vc_XInputGetState(unsigned player_index, VcXInputState *state);

int vc_xdk_open(const char *path, int flags, int mode);
ssize_t vc_xdk_read(int fd, void *buffer, size_t count);
ssize_t vc_xdk_write(int fd, const void *buffer, size_t count);
int vc_xdk_close(int fd);
int64_t vc_xdk_performance_counter(void);
uint64_t vc_xdk_performance_frequency(void);
void vc_xdk_sleep_ms(uint32_t milliseconds);
SDL_Thread *vc_xdk_create_thread(VcThreadFunction function, const char *name,
                                 void *context);

/*
 * These names mark the original-Xbox D3D8 boundary found by signatures.
 * The current host shell renders through OpenGL directly. PORTME: guest push
 * buffers, resources, shaders, and render-state encodings remain untranslated.
 */
void vc_D3DDevice_SetTexture(unsigned stage, unsigned guest_texture_handle);
void vc_D3DDevice_DrawIndexedVertices(unsigned primitive_type,
                                      unsigned vertex_count,
                                      unsigned guest_index_address);

#endif
