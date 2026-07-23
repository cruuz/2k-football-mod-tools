#include "port/model_animation.h"

#include <assimp/cimport.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int fail(const char *message)
{
    fprintf(stderr, "APF_PLAYER_SHADOW_RUNTIME_FAIL: %s\n", message);
    return EXIT_FAILURE;
}

static const struct aiScene *load_scene(const char *path)
{
    const unsigned int flags = aiProcess_Triangulate |
                               aiProcess_JoinIdenticalVertices |
                               aiProcess_GenSmoothNormals |
                               aiProcess_ImproveCacheLocality |
                               aiProcess_ValidateDataStructure;
    const struct aiScene *scene = aiImportFile(path, flags);
    if (scene == NULL) {
        fprintf(stderr, "Assimp: %s\n", aiGetErrorString());
    }
    return scene;
}

static VcModelVertex *source_vertices(const struct aiScene *scene)
{
    if (scene == NULL || scene->mNumMeshes != 1U || scene->mMeshes == NULL ||
        scene->mMeshes[0] == NULL || scene->mMeshes[0]->mNumVertices != 175U ||
        scene->mMeshes[0]->mVertices == NULL ||
        scene->mMeshes[0]->mNormals == NULL) {
        return NULL;
    }
    const struct aiMesh *mesh = scene->mMeshes[0];
    VcModelVertex *vertices =
        malloc((size_t)mesh->mNumVertices * sizeof(*vertices));
    if (vertices == NULL) {
        return NULL;
    }
    for (unsigned int i = 0; i < mesh->mNumVertices; ++i) {
        vertices[i] = (VcModelVertex){
            {mesh->mVertices[i].x, mesh->mVertices[i].y,
             mesh->mVertices[i].z},
            {mesh->mNormals[i].x, mesh->mNormals[i].y,
             mesh->mNormals[i].z},
        };
    }
    return vertices;
}

static int validate_static(const char *path)
{
    const struct aiScene *scene = load_scene(path);
    VcModelVertex *source = source_vertices(scene);
    VcModelVertex output[175];
    VcModelRuntime *runtime =
        source != NULL ? vc_model_runtime_create(scene, source, 175U) : NULL;
    const bool valid = scene != NULL && scene->mNumAnimations == 0U &&
                       scene->mMeshes[0]->mNumFaces == 306U &&
                       scene->mMeshes[0]->mNumBones == 21U &&
                       runtime != NULL &&
                       vc_model_runtime_bone_count(runtime) == 21U &&
                       vc_model_runtime_weight_count(runtime) == 181U &&
                       !vc_model_runtime_is_animated(runtime) &&
                       vc_model_runtime_deform(runtime, 0.0f, output, 175U);
    if (valid) {
        for (size_t i = 0; i < 175U; ++i) {
            for (size_t axis = 0; axis < 3U; ++axis) {
                if (!isfinite(output[i].position[axis]) ||
                    !isfinite(output[i].normal[axis])) {
                    vc_model_runtime_release(runtime);
                    free(source);
                    aiReleaseImport(scene);
                    return fail("static deformation produced a non-finite value");
                }
            }
        }
    }
    vc_model_runtime_release(runtime);
    free(source);
    if (scene != NULL) {
        aiReleaseImport(scene);
    }
    return valid ? EXIT_SUCCESS : fail("unexpected static host structure");
}

static int validate_animated(const char *path)
{
    const struct aiScene *scene = load_scene(path);
    VcModelVertex *source = source_vertices(scene);
    VcModelVertex at_start[175];
    VcModelVertex at_probe[175];
    VcModelRuntime *runtime =
        source != NULL ? vc_model_runtime_create(scene, source, 175U) : NULL;
    const bool structure = scene != NULL && scene->mNumAnimations == 1U &&
                           scene->mAnimations != NULL &&
                           scene->mAnimations[0] != NULL &&
                           scene->mAnimations[0]->mNumChannels == 18U &&
                           scene->mMeshes[0]->mNumFaces == 306U &&
                           scene->mMeshes[0]->mNumBones == 21U &&
                           runtime != NULL &&
                           vc_model_runtime_bone_count(runtime) == 21U &&
                           vc_model_runtime_weight_count(runtime) == 181U &&
                           vc_model_runtime_is_animated(runtime) &&
                           vc_model_runtime_deform(runtime, 0.0f, at_start,
                                                   175U) &&
                           vc_model_runtime_deform(runtime, 2.0f, at_probe,
                                                   175U);
    if (!structure) {
        vc_model_runtime_release(runtime);
        free(source);
        if (scene != NULL) {
            aiReleaseImport(scene);
        }
        return fail("unexpected animated host structure or deformation failure");
    }

    size_t moved = 0U;
    float maximum_delta_squared = 0.0f;
    for (size_t i = 0; i < 175U; ++i) {
        const float dx = at_probe[i].position[0] - at_start[i].position[0];
        const float dy = at_probe[i].position[1] - at_start[i].position[1];
        const float dz = at_probe[i].position[2] - at_start[i].position[2];
        const float delta_squared = dx * dx + dy * dy + dz * dz;
        if (!isfinite(delta_squared)) {
            vc_model_runtime_release(runtime);
            free(source);
            aiReleaseImport(scene);
            return fail("animated deformation produced a non-finite value");
        }
        if (delta_squared > 1.0e-12f) {
            ++moved;
        }
        maximum_delta_squared = fmaxf(maximum_delta_squared, delta_squared);
    }

    printf("APF_PLAYER_SHADOW_RUNTIME_PASS "
           "static_vertices=175 animated_vertices=175 faces=306 bones=21 "
           "weights=181 channels=18 moved=%zu max_delta=%.9g\n",
           moved, (double)sqrtf(maximum_delta_squared));
    vc_model_runtime_release(runtime);
    free(source);
    aiReleaseImport(scene);
    return moved == 175U && sqrtf(maximum_delta_squared) > 0.044f &&
                   sqrtf(maximum_delta_squared) < 0.046f
               ? EXIT_SUCCESS
               : fail("selected clip did not move every host vertex");
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        return fail("expected static and animated APF glTF paths");
    }
    if (validate_static(argv[1]) != EXIT_SUCCESS) {
        return EXIT_FAILURE;
    }
    return validate_animated(argv[2]);
}
