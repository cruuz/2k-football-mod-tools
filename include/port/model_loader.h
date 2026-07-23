#ifndef VC_PORT_MODEL_LOADER_H
#define VC_PORT_MODEL_LOADER_H

#include <stdbool.h>
#include <stddef.h>

struct aiScene;
struct VcModelRuntime;

typedef struct VcModel {
    const struct aiScene *scene;
    size_t mesh_count;
    size_t material_count;
    size_t animation_count;
    size_t bone_count;
    size_t bone_weight_count;
    size_t vertex_count;
    bool cpu_skinning_ready;
    unsigned int program;
    unsigned int vao;
    unsigned int vbo;
    unsigned int ebo;
    int index_count;
    float center[3];
    float radius;
    struct VcModelRuntime *runtime;
    char source_path[4096];
} VcModel;

bool vc_model_load(VcModel *model, const char *path);
void vc_model_render_preview(VcModel *model, int drawable_width,
                             int drawable_height, int x, int y, int width,
                             int height, float animation_seconds,
                             float angle_radians);
void vc_model_release(VcModel *model);

#endif
