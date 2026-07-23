#include "port/wav_audio.h"

#include <AL/alc.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct VcPcmWave {
    unsigned char *data;
    uint32_t data_size;
    uint32_t sample_rate;
    uint16_t channels;
    uint16_t bits_per_sample;
    uint16_t block_align;
} VcPcmWave;

static uint16_t read_u16le(const unsigned char *value)
{
    return (uint16_t)((uint16_t)value[0] |
                      ((uint16_t)value[1] << 8U));
}

static uint32_t read_u32le(const unsigned char *value)
{
    return (uint32_t)value[0] |
           ((uint32_t)value[1] << 8U) |
           ((uint32_t)value[2] << 16U) |
           ((uint32_t)value[3] << 24U);
}

static bool read_exact(FILE *stream, void *destination, size_t size)
{
    return size == 0U || fread(destination, 1U, size, stream) == size;
}

static bool skip_bytes(FILE *stream, uint32_t size)
{
    return size <= (uint32_t)LONG_MAX && fseek(stream, (long)size, SEEK_CUR) == 0;
}

static bool read_pcm_wave(const char *path, VcPcmWave *wave)
{
    memset(wave, 0, sizeof(*wave));
    FILE *stream = fopen(path, "rb");
    if (stream == NULL) {
        fprintf(stderr, "audio clip: could not open %s\n", path);
        return false;
    }

    unsigned char header[12];
    if (!read_exact(stream, header, sizeof(header)) ||
        memcmp(header, "RIFF", 4U) != 0 ||
        memcmp(header + 8U, "WAVE", 4U) != 0) {
        fprintf(stderr, "audio clip: %s is not a RIFF/WAVE file\n", path);
        fclose(stream);
        return false;
    }

    bool have_format = false;
    bool failed = false;
    for (;;) {
        unsigned char chunk[8];
        const size_t count = fread(chunk, 1U, sizeof(chunk), stream);
        if (count == 0U && feof(stream)) {
            break;
        }
        if (count != sizeof(chunk)) {
            failed = true;
            break;
        }
        const uint32_t chunk_size = read_u32le(chunk + 4U);
        if (memcmp(chunk, "fmt ", 4U) == 0) {
            unsigned char format[16];
            if (chunk_size < sizeof(format) ||
                !read_exact(stream, format, sizeof(format)) ||
                !skip_bytes(stream, chunk_size - (uint32_t)sizeof(format))) {
                failed = true;
                break;
            }
            const uint16_t format_tag = read_u16le(format);
            wave->channels = read_u16le(format + 2U);
            wave->sample_rate = read_u32le(format + 4U);
            wave->block_align = read_u16le(format + 12U);
            wave->bits_per_sample = read_u16le(format + 14U);
            have_format = format_tag == 1U;
            if (!have_format) {
                fprintf(stderr,
                        "audio clip: %s uses WAV format 0x%04x; "
                        "PORTME: decode non-PCM loose audio\n",
                        path, format_tag);
            }
        } else if (memcmp(chunk, "data", 4U) == 0 && wave->data == NULL) {
            if (chunk_size == 0U || chunk_size > (uint32_t)INT_MAX) {
                failed = true;
                break;
            }
            wave->data = malloc(chunk_size);
            if (wave->data == NULL ||
                !read_exact(stream, wave->data, chunk_size)) {
                failed = true;
                break;
            }
            wave->data_size = chunk_size;
        } else if (!skip_bytes(stream, chunk_size)) {
            failed = true;
            break;
        }
        if ((chunk_size & 1U) != 0U && !skip_bytes(stream, 1U)) {
            failed = true;
            break;
        }
    }
    fclose(stream);

    const uint32_t bytes_per_frame =
        (uint32_t)wave->channels * (uint32_t)wave->bits_per_sample / 8U;
    const bool supported = !failed && have_format && wave->data != NULL &&
                           (wave->channels == 1U || wave->channels == 2U) &&
                           (wave->bits_per_sample == 8U ||
                            wave->bits_per_sample == 16U) &&
                           wave->sample_rate > 0U &&
                           wave->sample_rate <= (uint32_t)INT_MAX &&
                           bytes_per_frame != 0U &&
                           wave->block_align == bytes_per_frame &&
                           wave->data_size % bytes_per_frame == 0U;
    if (!supported) {
        fprintf(stderr,
                "audio clip: could not load supported PCM data from %s "
                "(channels=%u bits=%u rate=%u align=%u bytes=%u)\n",
                path, wave->channels, wave->bits_per_sample,
                wave->sample_rate, wave->block_align, wave->data_size);
        free(wave->data);
        memset(wave, 0, sizeof(*wave));
        return false;
    }
    return true;
}

static ALenum openal_format(const VcPcmWave *wave)
{
    if (wave->channels == 1U) {
        return wave->bits_per_sample == 8U ? AL_FORMAT_MONO8 : AL_FORMAT_MONO16;
    }
    return wave->bits_per_sample == 8U ? AL_FORMAT_STEREO8 : AL_FORMAT_STEREO16;
}

bool vc_audio_clip_load(VcAudioClip *clip, const char *path)
{
    if (clip == NULL || path == NULL || strlen(path) >= sizeof(clip->source_path)) {
        return false;
    }
    vc_audio_clip_release(clip);
    if (alcGetCurrentContext() == NULL) {
        fprintf(stderr, "audio clip: OpenAL is unavailable; skipping %s\n", path);
        return false;
    }

    VcPcmWave wave;
    if (!read_pcm_wave(path, &wave)) {
        return false;
    }
    while (alGetError() != AL_NO_ERROR) {
    }
    alGenBuffers(1, &clip->buffer);
    if (alGetError() == AL_NO_ERROR) {
        alBufferData(clip->buffer, openal_format(&wave), wave.data,
                     (ALsizei)wave.data_size, (ALsizei)wave.sample_rate);
    }
    if (alGetError() == AL_NO_ERROR) {
        alGenSources(1, &clip->source);
    }
    if (alGetError() == AL_NO_ERROR) {
        alSourcei(clip->source, AL_BUFFER, (ALint)clip->buffer);
    }
    const ALenum error = alGetError();
    if (error != AL_NO_ERROR || clip->buffer == 0U || clip->source == 0U) {
        fprintf(stderr, "audio clip: OpenAL upload failed for %s (0x%04x)\n",
                path, (unsigned)error);
        free(wave.data);
        vc_audio_clip_release(clip);
        return false;
    }

    clip->sample_rate = wave.sample_rate;
    clip->frame_count = wave.data_size / wave.block_align;
    clip->channels = wave.channels;
    clip->bits_per_sample = wave.bits_per_sample;
    snprintf(clip->source_path, sizeof(clip->source_path), "%s", path);
    free(wave.data);
    fprintf(stderr,
            "audio clip: loaded %s (%u channels, %u Hz, %u frames, PCM%u)\n",
            path, clip->channels, clip->sample_rate, clip->frame_count,
            clip->bits_per_sample);
    return true;
}

void vc_audio_clip_play(VcAudioClip *clip)
{
    if (clip != NULL && clip->source != 0U && alcGetCurrentContext() != NULL) {
        alSourcePlay(clip->source);
    }
}

void vc_audio_clip_release(VcAudioClip *clip)
{
    if (clip == NULL) {
        return;
    }
    if (alcGetCurrentContext() != NULL) {
        if (clip->source != 0U) {
            alDeleteSources(1, &clip->source);
        }
        if (clip->buffer != 0U) {
            alDeleteBuffers(1, &clip->buffer);
        }
    }
    memset(clip, 0, sizeof(*clip));
}
