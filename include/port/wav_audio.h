#ifndef VC_PORT_WAV_AUDIO_H
#define VC_PORT_WAV_AUDIO_H

#include <AL/al.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct VcAudioClip {
    ALuint buffer;
    ALuint source;
    uint32_t sample_rate;
    uint32_t frame_count;
    uint16_t channels;
    uint16_t bits_per_sample;
    char source_path[4096];
} VcAudioClip;

bool vc_audio_clip_load(VcAudioClip *clip, const char *path);
void vc_audio_clip_play(VcAudioClip *clip);
void vc_audio_clip_release(VcAudioClip *clip);

#endif
