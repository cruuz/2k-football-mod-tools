#ifndef VC_PORT_MODEL_ANIMATION_H
#define VC_PORT_MODEL_ANIMATION_H

#include <stdbool.h>
#include <stddef.h>

struct aiScene;

typedef struct VcModelVertex {
    float position[3];
    float normal[3];
} VcModelVertex;

typedef struct VcModelRuntime VcModelRuntime;

/* Evaluates standard Assimp/glTF node animation and CPU skinning. This is a
   host-format seam only; it does not define either game's pose semantics. */
VcModelRuntime *vc_model_runtime_create(const struct aiScene *scene,
                                        const VcModelVertex *source_vertices,
                                        size_t vertex_count);
bool vc_model_runtime_deform(VcModelRuntime *runtime,
                             float animation_seconds,
                             VcModelVertex *output_vertices,
                             size_t output_vertex_count);
size_t vc_model_runtime_bone_count(const VcModelRuntime *runtime);
size_t vc_model_runtime_weight_count(const VcModelRuntime *runtime);
bool vc_model_runtime_is_animated(const VcModelRuntime *runtime);
void vc_model_runtime_release(VcModelRuntime *runtime);

#endif
