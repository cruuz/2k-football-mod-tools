#include "xdk/xdk_linux.h"

#include <AL/al.h>
#include <AL/alc.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

enum {
    VC_XINPUT_DPAD_UP = 0x0001,
    VC_XINPUT_DPAD_DOWN = 0x0002,
    VC_XINPUT_DPAD_LEFT = 0x0004,
    VC_XINPUT_DPAD_RIGHT = 0x0008,
    VC_XINPUT_START = 0x0010,
    VC_XINPUT_BACK = 0x0020,
    VC_XINPUT_LEFT_SHOULDER = 0x0100,
    VC_XINPUT_RIGHT_SHOULDER = 0x0200,
    VC_XINPUT_A = 0x1000,
    VC_XINPUT_B = 0x2000,
    VC_XINPUT_X = 0x4000,
    VC_XINPUT_Y = 0x8000
};

static SDL_GameController *controllers[4];
static ALCdevice *audio_device;
static ALCcontext *audio_context;
static VcXInputState previous_states[4];
static uint32_t packet_numbers[4];
static bool have_previous_state[4];

static SDL_JoystickID controller_instance(SDL_GameController *controller)
{
    SDL_Joystick *joystick = SDL_GameControllerGetJoystick(controller);
    return joystick != NULL ? SDL_JoystickInstanceID(joystick) : -1;
}

static void open_controller(int joystick_index)
{
    if (!SDL_IsGameController(joystick_index)) {
        return;
    }
    const SDL_JoystickID instance =
        SDL_JoystickGetDeviceInstanceID(joystick_index);
    if (instance < 0) {
        return;
    }
    for (size_t slot = 0; slot < 4; ++slot) {
        if (controllers[slot] != NULL &&
            controller_instance(controllers[slot]) == instance) {
            return;
        }
    }
    for (size_t slot = 0; slot < 4; ++slot) {
        if (controllers[slot] == NULL) {
            controllers[slot] = SDL_GameControllerOpen(joystick_index);
            if (controllers[slot] != NULL) {
                have_previous_state[slot] = false;
                packet_numbers[slot] = 0;
                fprintf(stderr, "input: controller %zu = %s\n", slot,
                        SDL_GameControllerName(controllers[slot]));
            }
            return;
        }
    }
}

bool vc_xdk_init(void)
{
    memset(controllers, 0, sizeof(controllers));
    memset(previous_states, 0, sizeof(previous_states));
    memset(packet_numbers, 0, sizeof(packet_numbers));
    memset(have_previous_state, 0, sizeof(have_previous_state));
    for (int i = 0; i < SDL_NumJoysticks(); ++i) {
        open_controller(i);
    }

    audio_device = alcOpenDevice(NULL);
    if (audio_device != NULL) {
        audio_context = alcCreateContext(audio_device, NULL);
        if (audio_context == NULL || !alcMakeContextCurrent(audio_context)) {
            fprintf(stderr, "audio: OpenAL context unavailable; continuing muted\n");
            if (audio_context != NULL) {
                alcDestroyContext(audio_context);
                audio_context = NULL;
            }
            alcCloseDevice(audio_device);
            audio_device = NULL;
        } else {
            fprintf(stderr, "audio: OpenAL initialized\n");
        }
    } else {
        fprintf(stderr, "audio: OpenAL device unavailable; continuing muted\n");
    }
    /* Loose PCM WAV clips can now use this context. PORTME: connect recovered
       title streaming, banks, voices, mixing, and APF XMA metadata. */
    return true;
}

void vc_xdk_shutdown(void)
{
    for (size_t i = 0; i < 4; ++i) {
        if (controllers[i] != NULL) {
            SDL_GameControllerClose(controllers[i]);
            controllers[i] = NULL;
            have_previous_state[i] = false;
        }
    }
    if (audio_context != NULL) {
        alcMakeContextCurrent(NULL);
        alcDestroyContext(audio_context);
        audio_context = NULL;
    }
    if (audio_device != NULL) {
        alcCloseDevice(audio_device);
        audio_device = NULL;
    }
}

void vc_xdk_handle_event(const SDL_Event *event)
{
    if (event == NULL) {
        return;
    }
    if (event->type == SDL_CONTROLLERDEVICEADDED) {
        open_controller(event->cdevice.which);
    } else if (event->type == SDL_CONTROLLERDEVICEREMOVED) {
        for (size_t i = 0; i < 4; ++i) {
            if (controllers[i] != NULL) {
                if (controller_instance(controllers[i]) ==
                    event->cdevice.which) {
                    SDL_GameControllerClose(controllers[i]);
                    controllers[i] = NULL;
                    have_previous_state[i] = false;
                    break;
                }
            }
        }
    }
}

static uint16_t button_mask(SDL_GameController *controller)
{
    uint16_t buttons = 0;
#define MAP_BUTTON(sdl_button, xdk_button) \
    do { if (SDL_GameControllerGetButton(controller, sdl_button)) buttons |= xdk_button; } while (0)
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_DPAD_UP, VC_XINPUT_DPAD_UP);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_DPAD_DOWN, VC_XINPUT_DPAD_DOWN);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_DPAD_LEFT, VC_XINPUT_DPAD_LEFT);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_DPAD_RIGHT, VC_XINPUT_DPAD_RIGHT);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_START, VC_XINPUT_START);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_BACK, VC_XINPUT_BACK);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_LEFTSHOULDER, VC_XINPUT_LEFT_SHOULDER);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, VC_XINPUT_RIGHT_SHOULDER);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_A, VC_XINPUT_A);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_B, VC_XINPUT_B);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_X, VC_XINPUT_X);
    MAP_BUTTON(SDL_CONTROLLER_BUTTON_Y, VC_XINPUT_Y);
#undef MAP_BUTTON
    return buttons;
}

static uint8_t trigger_value(Sint16 axis)
{
    return axis <= 0 ? 0 : (uint8_t)((uint32_t)axis * 255U / 32767U);
}

static int16_t xinput_y_axis(Sint16 axis)
{
    /* SDL is positive-down; XInput thumb Y is positive-up. */
    return axis == INT16_MIN ? INT16_MAX : (int16_t)-axis;
}

int vc_XInputGetState(unsigned player_index, VcXInputState *state)
{
    if (state == NULL) {
        return -1;
    }
    memset(state, 0, sizeof(*state));
    if (player_index >= 4 || controllers[player_index] == NULL ||
        !SDL_GameControllerGetAttached(controllers[player_index])) {
        return -1;
    }
    SDL_GameController *controller = controllers[player_index];
    VcXInputState next = {0};
    next.packet_number = packet_numbers[player_index];
    next.buttons = button_mask(controller);
    next.left_trigger = trigger_value(SDL_GameControllerGetAxis(
        controller, SDL_CONTROLLER_AXIS_TRIGGERLEFT));
    next.right_trigger = trigger_value(SDL_GameControllerGetAxis(
        controller, SDL_CONTROLLER_AXIS_TRIGGERRIGHT));
    next.thumb_lx = SDL_GameControllerGetAxis(controller,
                                              SDL_CONTROLLER_AXIS_LEFTX);
    next.thumb_ly = xinput_y_axis(SDL_GameControllerGetAxis(
        controller, SDL_CONTROLLER_AXIS_LEFTY));
    next.thumb_rx = SDL_GameControllerGetAxis(controller,
                                              SDL_CONTROLLER_AXIS_RIGHTX);
    next.thumb_ry = xinput_y_axis(SDL_GameControllerGetAxis(
        controller, SDL_CONTROLLER_AXIS_RIGHTY));
    if (!have_previous_state[player_index] ||
        memcmp(&next, &previous_states[player_index], sizeof(next)) != 0) {
        next.packet_number = ++packet_numbers[player_index];
        previous_states[player_index] = next;
        have_previous_state[player_index] = true;
    }
    *state = next;
    return 0;
}

int vc_xdk_open(const char *path, int flags, int mode)
{
    /* PORTME: translate recovered Xbox device prefixes, mount points, share
       modes, overlapped I/O, and error codes before guest callers use this. */
    return open(path, flags, (mode_t)mode);
}

ssize_t vc_xdk_read(int fd, void *buffer, size_t count)
{
    return read(fd, buffer, count);
}

ssize_t vc_xdk_write(int fd, const void *buffer, size_t count)
{
    return write(fd, buffer, count);
}

int vc_xdk_close(int fd)
{
    return close(fd);
}

int64_t vc_xdk_performance_counter(void)
{
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return (int64_t)value.tv_sec * 1000000000LL + value.tv_nsec;
}

uint64_t vc_xdk_performance_frequency(void)
{
    return 1000000000ULL;
}

void vc_xdk_sleep_ms(uint32_t milliseconds)
{
    SDL_Delay(milliseconds);
}

SDL_Thread *vc_xdk_create_thread(VcThreadFunction function, const char *name,
                                 void *context)
{
    return SDL_CreateThread(function, name, context);
}

void vc_D3DDevice_SetTexture(unsigned stage, unsigned guest_texture_handle)
{
    static bool warned;
    if (!warned) {
        fprintf(stderr,
                "PORTME: D3D8 SetTexture guest descriptors are not translated "
                "yet (stage=%u handle=0x%08x)\n",
                stage, guest_texture_handle);
        warned = true;
    }
}

void vc_D3DDevice_DrawIndexedVertices(unsigned primitive_type,
                                      unsigned vertex_count,
                                      unsigned guest_index_address)
{
    static bool warned;
    if (!warned) {
        fprintf(stderr,
                "PORTME: D3D8 guest vertex/index declarations are not "
                "translated yet (primitive=%u vertices=%u index=0x%08x)\n",
                primitive_type, vertex_count, guest_index_address);
        warned = true;
    }
}
