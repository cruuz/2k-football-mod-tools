/* Independent Assimp import smoke for the static NFL 2K5 HI_res skin. */

#include <assimp/cimport.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned int count_joint_nodes(const struct aiNode *node)
{
    unsigned int count = 0U;
    if (node == NULL) {
        return 0U;
    }
    if (strncmp(node->mName.data, "HI_res:", 7U) == 0) {
        count = 1U;
    }
    for (unsigned int i = 0U; i < node->mNumChildren; ++i) {
        count += count_joint_nodes(node->mChildren[i]);
    }
    return count;
}

static int fail(const char *message)
{
    fprintf(stderr, "NFL_HI_BODY_ASSIMP_FAIL: %s\n", message);
    return EXIT_FAILURE;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        return fail("expected one glTF path");
    }
    const unsigned int flags = aiProcess_Triangulate |
                               aiProcess_JoinIdenticalVertices |
                               aiProcess_ValidateDataStructure;
    const struct aiScene *scene = aiImportFile(argv[1], flags);
    if (scene == NULL) {
        fprintf(stderr, "Assimp: %s\n", aiGetErrorString());
        return fail("import failed");
    }
    if (scene->mNumMeshes != 86U || scene->mNumAnimations != 0U ||
        scene->mRootNode == NULL) {
        aiReleaseImport(scene);
        return fail("scene mesh/animation/root count differs");
    }
    const unsigned int joint_nodes = count_joint_nodes(scene->mRootNode);
    if (joint_nodes != 62U) {
        aiReleaseImport(scene);
        return fail("62-joint node hierarchy was not retained");
    }

    size_t total_vertices = 0U;
    size_t total_faces = 0U;
    size_t total_bones = 0U;
    size_t total_weights = 0U;
    size_t active_weights = 0U;
    size_t zero_weights = 0U;
    float maximum_weight_sum_error = 0.0F;
    for (unsigned int mesh_index = 0U; mesh_index < scene->mNumMeshes; ++mesh_index) {
        const struct aiMesh *mesh = scene->mMeshes[mesh_index];
        if (mesh == NULL || mesh->mNumVertices == 0U || mesh->mNumFaces == 0U ||
            mesh->mNumBones == 0U || mesh->mVertices == NULL) {
            aiReleaseImport(scene);
            return fail("imported mesh lacks geometry or skin bones");
        }
        float *weight_sums = calloc(mesh->mNumVertices, sizeof(*weight_sums));
        if (weight_sums == NULL) {
            aiReleaseImport(scene);
            return fail("weight accumulator allocation failed");
        }
        for (unsigned int vertex = 0U; vertex < mesh->mNumVertices; ++vertex) {
            const struct aiVector3D p = mesh->mVertices[vertex];
            if (!isfinite(p.x) || !isfinite(p.y) || !isfinite(p.z)) {
                free(weight_sums);
                aiReleaseImport(scene);
                return fail("imported position is non-finite");
            }
        }
        for (unsigned int bone_index = 0U; bone_index < mesh->mNumBones; ++bone_index) {
            const struct aiBone *bone = mesh->mBones[bone_index];
            if (bone == NULL || bone->mNumWeights == 0U) {
                free(weight_sums);
                aiReleaseImport(scene);
                return fail("imported bone has no weights");
            }
            for (unsigned int weight_index = 0U;
                 weight_index < bone->mNumWeights; ++weight_index) {
                const struct aiVertexWeight weight = bone->mWeights[weight_index];
                if (weight.mVertexId >= mesh->mNumVertices ||
                    !isfinite(weight.mWeight) || weight.mWeight < 0.0F ||
                    weight.mWeight > 1.0F) {
                    fprintf(stderr,
                            "mesh=%u bone=%u weight=%u vertex=%u value=%.9g vertices=%u\n",
                            mesh_index, bone_index, weight_index,
                            weight.mVertexId, (double)weight.mWeight,
                            mesh->mNumVertices);
                    free(weight_sums);
                    aiReleaseImport(scene);
                    return fail("imported vertex weight differs");
                }
                weight_sums[weight.mVertexId] += weight.mWeight;
                if (weight.mWeight == 0.0F) {
                    ++zero_weights;
                }
                else {
                    ++active_weights;
                }
                ++total_weights;
            }
        }
        for (unsigned int vertex = 0U; vertex < mesh->mNumVertices; ++vertex) {
            const float error = fabsf(weight_sums[vertex] - 1.0F);
            if (error > maximum_weight_sum_error) {
                maximum_weight_sum_error = error;
            }
            if (error > 1.0e-5F) {
                free(weight_sums);
                aiReleaseImport(scene);
                return fail("imported active weights do not sum to one");
            }
        }
        free(weight_sums);
        total_vertices += mesh->mNumVertices;
        total_faces += mesh->mNumFaces;
        total_bones += mesh->mNumBones;
    }
    printf(
        "NFL_HI_BODY_ASSIMP_PASS meshes=%u joint_nodes=%u vertices=%zu "
        "faces=%zu bones=%zu weights=%zu active_weights=%zu zero_weights=%zu "
        "max_weight_error=%.9g\n",
        scene->mNumMeshes, joint_nodes, total_vertices, total_faces,
        total_bones, total_weights, active_weights, zero_weights,
        (double)maximum_weight_sum_error
    );
    aiReleaseImport(scene);
    return EXIT_SUCCESS;
}
