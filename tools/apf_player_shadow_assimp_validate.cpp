#include <assimp/Importer.hpp>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {

[[noreturn]] void fail(const std::string &message) {
    std::cerr << "APF_PLAYER_SHADOW_ASSIMP_VALIDATION_FAIL " << message << '\n';
    std::exit(1);
}

void require(bool condition, const std::string &message) {
    if (!condition) fail(message);
}

constexpr std::array<const char *, 21> kJoints = {
    "root", "r_hip_hinge_base", "r_femur", "r_knee_hinge", "r_ankle",
    "l_hip_hinge_base", "l_femur", "l_knee_hinge", "l_ankle", "thorax",
    "l_clavicle", "l_shoulder_hinge_base", "l_humerus", "l_elbow",
    "l_hand", "head", "r_clavicle", "r_shoulder_hinge_base", "r_humerus",
    "r_elbow", "r_hand",
};

constexpr std::array<int, 17> kRotationJoints = {
    0, 2, 3, 4, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 18, 19, 20,
};

constexpr std::array<int, 6> kTranslationJoints = {2, 6, 9, 12, 15, 18};

const aiScene *load(Assimp::Importer &importer, const char *path) {
    const aiScene *scene = importer.ReadFile(
        path, aiProcess_ValidateDataStructure | aiProcess_Triangulate);
    if (scene == nullptr) fail(std::string("cannot import ") + path + ": " +
                               importer.GetErrorString());
    require(scene->mRootNode != nullptr, "missing imported root node");
    return scene;
}

const aiNode *find_node(const aiScene *scene, const char *name) {
    return scene->mRootNode->FindNode(aiString(name));
}

void validate_nodes(const aiScene *scene) {
    require(find_node(scene, "player_shadow_external_root") != nullptr,
            "external-root node is absent");
    require(find_node(scene, "player_shadow_mesh") != nullptr,
            "mesh node is absent");
    for (const char *name : kJoints) {
        require(find_node(scene, name) != nullptr,
                std::string("joint node is absent: ") + name);
    }
}

void validate_mesh(const aiScene *scene) {
    require(scene->mNumMeshes == 1, "expected one mesh");
    const aiMesh *mesh = scene->mMeshes[0];
    require(mesh->mNumVertices == 351, "expected 351 vertices");
    require(mesh->mNumFaces == 306, "expected 306 triangles");
    for (unsigned index = 0; index < mesh->mNumFaces; ++index) {
        require(mesh->mFaces[index].mNumIndices == 3, "non-triangle face imported");
    }

    aiVector3D minimum = mesh->mVertices[0];
    aiVector3D maximum = mesh->mVertices[0];
    for (unsigned index = 1; index < mesh->mNumVertices; ++index) {
        const aiVector3D &value = mesh->mVertices[index];
        minimum.x = std::min(minimum.x, value.x);
        minimum.y = std::min(minimum.y, value.y);
        minimum.z = std::min(minimum.z, value.z);
        maximum.x = std::max(maximum.x, value.x);
        maximum.y = std::max(maximum.y, value.y);
        maximum.z = std::max(maximum.z, value.z);
    }
    require(maximum.y - minimum.y > 1.8f && maximum.y - minimum.y < 2.0f,
            "mesh is not in the expected meter-scale human range");

    require(mesh->mNumBones == 21, "Assimp did not retain all 21 skin joints");
    std::unordered_set<std::string> bone_names;
    std::vector<unsigned> positive_count(mesh->mNumVertices, 0);
    std::vector<double> weight_sum(mesh->mNumVertices, 0.0);
    for (unsigned bone_index = 0; bone_index < mesh->mNumBones; ++bone_index) {
        const aiBone *bone = mesh->mBones[bone_index];
        bone_names.emplace(bone->mName.C_Str());
        for (unsigned weight_index = 0; weight_index < bone->mNumWeights;
             ++weight_index) {
            const aiVertexWeight &weight = bone->mWeights[weight_index];
            require(weight.mVertexId < mesh->mNumVertices, "bone vertex out of range");
            if (weight.mWeight > 0.0f) {
                ++positive_count[weight.mVertexId];
                weight_sum[weight.mVertexId] += weight.mWeight;
            }
        }
    }
    for (const char *name : kJoints) {
        require(bone_names.contains(name),
                std::string("skin bone is absent: ") + name);
    }
    for (unsigned vertex = 0; vertex < mesh->mNumVertices; ++vertex) {
        require(positive_count[vertex] == 1,
                "vertex does not have exactly one positive Assimp influence");
        if (std::abs(weight_sum[vertex] - 1.0) >= 1e-6) {
            std::ostringstream message;
            message << "vertex Assimp weight does not sum to one: vertex="
                    << vertex << " sum=" << std::setprecision(17)
                    << weight_sum[vertex];
            fail(message.str());
        }
    }
}

const aiNodeAnim *find_channel(const aiAnimation *animation, const char *name) {
    for (unsigned index = 0; index < animation->mNumChannels; ++index) {
        if (animation->mChannels[index]->mNodeName == aiString(name))
            return animation->mChannels[index];
    }
    return nullptr;
}

void validate_animation(const aiScene *scene) {
    require(scene->mNumAnimations == 1, "expected one animation");
    const aiAnimation *animation = scene->mAnimations[0];
    require(std::string(animation->mName.C_Str()).find(
                "mnu_stn_01_070130_01_lg") != std::string::npos,
            "selected clip name is absent");
    require(animation->mNumChannels == 18,
            "expected 17 joint nodes plus one external-root channel");
    const double ticks_per_second = animation->mTicksPerSecond == 0.0
        ? 1.0 : animation->mTicksPerSecond;
    const double seconds = animation->mDuration / ticks_per_second;
    require(std::abs(seconds - 7.7166666984558105) < 1e-5,
            "animation duration changed");

    const aiNodeAnim *external = find_channel(animation,
                                               "player_shadow_external_root");
    require(external != nullptr, "external-root animation channel is absent");
    require(external->mNumPositionKeys == 927,
            "external-root key count changed");

    std::unordered_set<int> translations(kTranslationJoints.begin(),
                                         kTranslationJoints.end());
    for (int joint : kRotationJoints) {
        const aiNodeAnim *channel = find_channel(animation, kJoints[joint]);
        require(channel != nullptr,
                std::string("rotation channel is absent: ") + kJoints[joint]);
        require(channel->mNumRotationKeys == 927,
                std::string("rotation key count changed: ") + kJoints[joint]);
        if (translations.contains(joint)) {
            require(channel->mNumPositionKeys == 927,
                    std::string("translation key count changed: ") + kJoints[joint]);
        }
        for (unsigned key = 0; key < channel->mNumRotationKeys; ++key) {
            const aiQuaternion &value = channel->mRotationKeys[key].mValue;
            const double norm = std::sqrt(value.w * value.w + value.x * value.x +
                                          value.y * value.y + value.z * value.z);
            require(std::abs(norm - 1.0) < 2e-5,
                    "imported quaternion is not normalized");
        }
    }
}

} // namespace

int main(int argc, char **argv) {
    if (argc != 3) {
        std::cerr << "usage: " << argv[0] << " static.gltf animated.gltf\n";
        return 2;
    }
    Assimp::Importer static_importer;
    const aiScene *static_scene = load(static_importer, argv[1]);
    validate_nodes(static_scene);
    validate_mesh(static_scene);
    require(static_scene->mNumAnimations == 0,
            "canonical static skin unexpectedly has animation");

    Assimp::Importer animated_importer;
    const aiScene *animated_scene = load(animated_importer, argv[2]);
    validate_nodes(animated_scene);
    validate_mesh(animated_scene);
    validate_animation(animated_scene);

    std::cout << "APF_PLAYER_SHADOW_ASSIMP_VALIDATION_PASS "
                 "vertices=351 triangles=306 joints=21 one_hot=351 "
                 "animations=1 keys=927 channels=18\n";
    return 0;
}
