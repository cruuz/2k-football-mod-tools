#include "port/model_animation.h"

#include <assimp/cimport.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static int fail(const char *message)
{
    fprintf(stderr, "MODEL_ANIMATION_RUNTIME_FAIL: %s\n", message);
    return EXIT_FAILURE;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        return fail("expected one glTF fixture path");
    }
    const unsigned int flags = aiProcess_Triangulate |
                               aiProcess_JoinIdenticalVertices |
                               aiProcess_GenSmoothNormals |
                               aiProcess_ValidateDataStructure;
    const struct aiScene *scene = aiImportFile(argv[1], flags);
    if (scene == NULL) {
        fprintf(stderr, "Assimp: %s\n", aiGetErrorString());
        return fail("fixture import failed");
    }
    if (scene->mNumMeshes != 1U || scene->mMeshes[0] == NULL ||
        scene->mMeshes[0]->mNumVertices != 3U ||
        scene->mNumAnimations != 1U) {
        aiReleaseImport(scene);
        return fail("unexpected imported fixture structure");
    }

    const struct aiMesh *mesh = scene->mMeshes[0];
    VcModelVertex source[3];
    for (size_t i = 0; i < 3U; ++i) {
        source[i] = (VcModelVertex){
            {mesh->mVertices[i].x, mesh->mVertices[i].y,
             mesh->mVertices[i].z},
            {mesh->mNormals[i].x, mesh->mNormals[i].y,
             mesh->mNormals[i].z}};
    }
    VcModelRuntime *runtime = vc_model_runtime_create(scene, source, 3U);
    if (runtime == NULL || vc_model_runtime_bone_count(runtime) != 1U ||
        vc_model_runtime_weight_count(runtime) != 3U ||
        !vc_model_runtime_is_animated(runtime)) {
        vc_model_runtime_release(runtime);
        aiReleaseImport(scene);
        return fail("runtime did not retain the one-joint skin");
    }

    VcModelVertex at_zero[3];
    VcModelVertex at_half[3];
    VcModelVertex at_one[3];
    if (!vc_model_runtime_deform(runtime, 0.0f, at_zero, 3U) ||
        !vc_model_runtime_deform(runtime, 0.5f, at_half, 3U) ||
        !vc_model_runtime_deform(runtime, 1.0f, at_one, 3U)) {
        vc_model_runtime_release(runtime);
        aiReleaseImport(scene);
        return fail("deformation evaluation failed");
    }
    for (size_t i = 0; i < 3U; ++i) {
        if (fabsf(at_zero[i].position[0] - source[i].position[0]) > 1.0e-6f ||
            fabsf(at_half[i].position[0] -
                  (source[i].position[0] + 0.5f)) > 1.0e-6f ||
            fabsf(at_one[i].position[0] -
                  (source[i].position[0] + 1.0f)) > 1.0e-6f ||
            fabsf(at_one[i].position[1] - source[i].position[1]) > 1.0e-6f ||
            fabsf(at_one[i].normal[2] - 1.0f) > 1.0e-6f) {
            vc_model_runtime_release(runtime);
            aiReleaseImport(scene);
            return fail("linear joint translation did not deform exactly");
        }
    }

    printf("MODEL_ANIMATION_RUNTIME_PASS bones=1 weights=3 delta=1\n");
    vc_model_runtime_release(runtime);
    aiReleaseImport(scene);
    return EXIT_SUCCESS;
}
