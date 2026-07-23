cmake_minimum_required(VERSION 3.20)

project(vc_football_linux_port VERSION 0.1.0 LANGUAGES C)

include(GNUInstallDirs)
include(CTest)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(VC_PORT_STRICT "Treat compiler warnings as errors" OFF)
option(VC_PORT_ENABLE_GL_TESTS
       "Register smoke tests that require a working OpenGL display" ON)
option(VC_PORT_ENABLE_APF_BOOT_LEAF_TESTS
       "Build isolated APF guest-ABI leaf-adapter tests" ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SDL2 REQUIRED IMPORTED_TARGET sdl2)
find_package(OpenGL REQUIRED)
find_package(GLEW REQUIRED)
find_package(OpenAL REQUIRED)
find_package(PNG REQUIRED)
find_package(assimp REQUIRED)

add_executable(vc_football_port
    src/main.c
    src/assets/model_animation.c
    src/assets/model_loader.c
    src/assets/bitmap_font_metrics.c
    src/assets/png_texture.c
    src/audio/wav_audio.c
    src/platform/xdk_linux.c
    src/recovered/apf2k8/packed_pose.c
    src/recovered/apf2k8/translation_pose.c
    src/recovered/nfl2k5/coach_ref_pose.c
    src/recovered/nfl2k5/motion_event.c
    src/recovered/nfl2k5/motion_pose_sample.c
    src/recovered/nfl2k5/formatted_token.c
    src/recovered/nfl2k5/main_menu_row_layout.c
    src/recovered/nfl2k5/packed_pose.c
    src/recovered/nfl2k5/player_pose.c
    src/recovered/nfl2k5/player_current_postprocess.c
    src/recovered/nfl2k5/player_local_postprocess.c
    src/recovered/nfl2k5/quaternion_interpolation.c
    src/recovered/nfl2k5/trajectory.c
    src/recovered/shared/menu_model.c
    src/recovered/shared/side_label.c
    src/recovered/shared/value_bucket.c
    src/render/bitmap_font.c
    src/render/ui_renderer.c
)

set(VC_INSTALL_ASSET_DIR
    "${CMAKE_INSTALL_FULL_DATADIR}/${PROJECT_NAME}/assets/mod/common")
file(RELATIVE_PATH VC_INSTALL_ASSET_RELATIVE
     "${CMAKE_INSTALL_FULL_BINDIR}" "${VC_INSTALL_ASSET_DIR}")

target_include_directories(vc_football_port PRIVATE include)
target_link_libraries(vc_football_port PRIVATE
    PkgConfig::SDL2
    OpenGL::GL
    GLEW::GLEW
    OpenAL::OpenAL
    PNG::PNG
    assimp::assimp
    m
)

target_compile_definitions(vc_football_port PRIVATE
    _POSIX_C_SOURCE=200809L
    VC_PORT_VERSION="${PROJECT_VERSION}"
    VC_INSTALL_ASSET_RELATIVE="${VC_INSTALL_ASSET_RELATIVE}"
)

if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(vc_football_port PRIVATE
        -Wall
        -Wextra
        -Wpedantic
        -Wconversion
        -Wshadow
        $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
    )
endif()

install(TARGETS vc_football_port RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY assets/mod/common
        DESTINATION ${CMAKE_INSTALL_DATADIR}/${PROJECT_NAME}/assets/mod)

if(BUILD_TESTING)
    if(VC_PORT_ENABLE_APF_BOOT_LEAF_TESTS)
        add_executable(vc_apf_boot_leaf_adapter_tests
            tests/apf_boot_leaf_adapters_test.c
            src/static_runtime/apf_boot_leaf_adapters.c
        )
        target_include_directories(vc_apf_boot_leaf_adapter_tests PRIVATE include)
        if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
            target_compile_options(vc_apf_boot_leaf_adapter_tests PRIVATE
                -Wall -Wextra -Wpedantic -Wconversion -Wshadow
                $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
            )
        endif()
        add_test(NAME apf_boot_leaf_adapter_semantics
                 COMMAND $<TARGET_FILE:vc_apf_boot_leaf_adapter_tests>)
        set_tests_properties(apf_boot_leaf_adapter_semantics PROPERTIES
            LABELS "static_runtime;apf"
            PASS_REGULAR_EXPRESSION
                "APF_BOOT_LEAF_ADAPTERS_PASS resumable_imports=24 terminal_imports=4 exception_imports=1 direct_sites=87 proved_indirect_import_sites=4.*thread_create_sites=1 thread_create_requests=1 unsupported_frontier_imports=0")

        add_executable(vc_apf_first_entry_gate_tests
            tests/apf_first_entry_gate_test.c
            src/static_runtime/apf_first_entry_gate.c
            src/static_runtime/apf_imported_data_bootstrap.c
            src/static_runtime/apf_boot_leaf_adapters.c
        )
        target_include_directories(vc_apf_first_entry_gate_tests PRIVATE include)
        if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
            target_compile_options(vc_apf_first_entry_gate_tests PRIVATE
                -Wall -Wextra -Wpedantic -Wconversion -Wshadow
                $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
            )
        endif()
        add_test(NAME apf_first_entry_gate_semantics
                 COMMAND $<TARGET_FILE:vc_apf_first_entry_gate_tests>)
        set_tests_properties(apf_first_entry_gate_semantics PROPERTIES
            LABELS "static_runtime;apf"
            PASS_REGULAR_EXPRESSION
                "APF_FIRST_ENTRY_GATE_PASS bindings=30 resumable=24 terminal=4 exception=1 thread_create=1 blockers=3 entry_authorized=0 entry_called=0 containment=3")
    endif()

    add_executable(vc_recovered_shared_tests
        tests/recovered_shared_test.c
        src/recovered/shared/side_label.c
        src/recovered/shared/value_bucket.c
    )
    target_include_directories(vc_recovered_shared_tests PRIVATE include)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_recovered_shared_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_shared_semantics
             COMMAND $<TARGET_FILE:vc_recovered_shared_tests>)
    set_tests_properties(recovered_shared_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "RECOVERED_SHARED_PASS")

    add_executable(vc_recovered_menu_model_tests
        tests/recovered_menu_model_test.c
        src/recovered/shared/menu_model.c
    )
    target_include_directories(vc_recovered_menu_model_tests PRIVATE include)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_recovered_menu_model_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_menu_model_semantics
             COMMAND $<TARGET_FILE:vc_recovered_menu_model_tests>)
    set_tests_properties(recovered_menu_model_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "RECOVERED_MENU_MODEL_PASS")

    add_executable(vc_apf_packed_pose_tests
        tests/apf_packed_pose_test.c
        src/recovered/apf2k8/packed_pose.c
    )
    target_include_directories(vc_apf_packed_pose_tests PRIVATE include)
    target_link_libraries(vc_apf_packed_pose_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_apf_packed_pose_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_apf_packed_pose_semantics
             COMMAND $<TARGET_FILE:vc_apf_packed_pose_tests>)
    set_tests_properties(recovered_apf_packed_pose_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "APF_PACKED_POSE_NATIVE_PASS")

    add_executable(vc_apf_translation_pose_tests
        tests/apf_translation_pose_test.c
        src/recovered/apf2k8/translation_pose.c
    )
    target_include_directories(vc_apf_translation_pose_tests PRIVATE include)
    target_link_libraries(vc_apf_translation_pose_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_apf_translation_pose_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_apf_translation_pose_semantics
             COMMAND $<TARGET_FILE:vc_apf_translation_pose_tests>)
    set_tests_properties(recovered_apf_translation_pose_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "APF_TRANSLATION_POSE_NATIVE_PASS")

    add_executable(vc_nfl_packed_pose_tests
        tests/nfl_packed_pose_test.c
        src/recovered/nfl2k5/packed_pose.c
    )
    target_include_directories(vc_nfl_packed_pose_tests PRIVATE include)
    target_link_libraries(vc_nfl_packed_pose_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_packed_pose_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_packed_pose_semantics
             COMMAND $<TARGET_FILE:vc_nfl_packed_pose_tests>)
    set_tests_properties(recovered_nfl_packed_pose_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "NFL_PACKED_POSE_NATIVE_PASS")

    add_executable(vc_nfl_trajectory_tests
        tests/nfl_trajectory_test.c
        src/recovered/nfl2k5/trajectory.c
    )
    target_include_directories(vc_nfl_trajectory_tests PRIVATE include)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_trajectory_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_trajectory_semantics
             COMMAND $<TARGET_FILE:vc_nfl_trajectory_tests>)
    set_tests_properties(recovered_nfl_trajectory_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "NFL_TRAJECTORY_NATIVE_PASS")

    add_executable(vc_nfl_motion_event_tests
        tests/nfl_motion_event_test.c
        src/recovered/nfl2k5/motion_event.c
    )
    target_include_directories(vc_nfl_motion_event_tests PRIVATE include)
    target_link_libraries(vc_nfl_motion_event_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_motion_event_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_motion_event_semantics
             COMMAND $<TARGET_FILE:vc_nfl_motion_event_tests>)
    set_tests_properties(recovered_nfl_motion_event_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "NFL_MOTION_EVENT_NATIVE_PASS")

    add_executable(vc_nfl_quaternion_interpolation_tests
        tests/nfl_quaternion_interpolation_test.c
        src/recovered/nfl2k5/quaternion_interpolation.c
    )
    target_include_directories(vc_nfl_quaternion_interpolation_tests PRIVATE include)
    target_link_libraries(vc_nfl_quaternion_interpolation_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_quaternion_interpolation_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_quaternion_interpolation_semantics
             COMMAND $<TARGET_FILE:vc_nfl_quaternion_interpolation_tests>)
    set_tests_properties(recovered_nfl_quaternion_interpolation_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "NFL_QUATERNION_INTERPOLATION_NATIVE_PASS")

    add_executable(vc_nfl_motion_pose_sample_tests
        tests/nfl_motion_pose_sample_test.c
        src/recovered/nfl2k5/motion_pose_sample.c
        src/recovered/nfl2k5/packed_pose.c
        src/recovered/nfl2k5/quaternion_interpolation.c
    )
    target_include_directories(vc_nfl_motion_pose_sample_tests PRIVATE include)
    target_link_libraries(vc_nfl_motion_pose_sample_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_motion_pose_sample_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_motion_pose_sample_semantics
             COMMAND $<TARGET_FILE:vc_nfl_motion_pose_sample_tests>)
    set_tests_properties(recovered_nfl_motion_pose_sample_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "NFL_MOTION_POSE_SAMPLE_NATIVE_PASS")

    add_executable(vc_nfl_coach_ref_pose_tests
        tests/nfl_coach_ref_pose_test.c
        src/recovered/nfl2k5/coach_ref_pose.c
        src/recovered/nfl2k5/motion_pose_sample.c
        src/recovered/nfl2k5/packed_pose.c
        src/recovered/nfl2k5/quaternion_interpolation.c
    )
    target_include_directories(vc_nfl_coach_ref_pose_tests PRIVATE include)
    target_link_libraries(vc_nfl_coach_ref_pose_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_coach_ref_pose_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_coach_ref_pose_semantics
             COMMAND $<TARGET_FILE:vc_nfl_coach_ref_pose_tests>)
    set_tests_properties(recovered_nfl_coach_ref_pose_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION
            "NFL_COACH_REF_POSE_NATIVE_PASS channels=25 packed=21 disabled=4")

    add_executable(vc_nfl_player_pose_tests
        tests/nfl_player_pose_test.c
        src/recovered/nfl2k5/player_pose.c
        src/recovered/nfl2k5/motion_pose_sample.c
        src/recovered/nfl2k5/packed_pose.c
        src/recovered/nfl2k5/quaternion_interpolation.c
    )
    target_include_directories(vc_nfl_player_pose_tests PRIVATE include)
    target_link_libraries(vc_nfl_player_pose_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_player_pose_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_player_pose_semantics
             COMMAND $<TARGET_FILE:vc_nfl_player_pose_tests>)
    set_tests_properties(recovered_nfl_player_pose_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION
            "NFL_PLAYER_POSE_NATIVE_PASS channels=25 packed=23 disabled=2")

    add_executable(vc_nfl_player_current_postprocess_tests
        tests/nfl_player_current_postprocess_test.c
        src/recovered/nfl2k5/player_current_postprocess.c
    )
    target_include_directories(vc_nfl_player_current_postprocess_tests PRIVATE include)
    target_link_libraries(vc_nfl_player_current_postprocess_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_player_current_postprocess_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_player_current_postprocess_semantics
             COMMAND $<TARGET_FILE:vc_nfl_player_current_postprocess_tests>)
    set_tests_properties(
        recovered_nfl_player_current_postprocess_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "NFL_PLAYER_CURRENT_POSTPROCESS_TEST_PASS")

    add_executable(vc_nfl_player_local_postprocess_tests
        tests/nfl_player_local_postprocess_test.c
        src/recovered/nfl2k5/player_local_postprocess.c
    )
    target_include_directories(vc_nfl_player_local_postprocess_tests PRIVATE include)
    target_link_libraries(vc_nfl_player_local_postprocess_tests PRIVATE m)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_player_local_postprocess_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_player_local_postprocess_semantics
             COMMAND $<TARGET_FILE:vc_nfl_player_local_postprocess_tests>)
    set_tests_properties(
        recovered_nfl_player_local_postprocess_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION "NFL_PLAYER_LOCAL_POSTPROCESS_TEST_PASS")

    add_executable(vc_nfl_main_menu_row_layout_tests
        tests/nfl_main_menu_row_layout_test.c
        src/recovered/nfl2k5/main_menu_row_layout.c
    )
    target_include_directories(
        vc_nfl_main_menu_row_layout_tests PRIVATE include)
    if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
        target_compile_options(vc_nfl_main_menu_row_layout_tests PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wshadow
            $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
        )
    endif()
    add_test(NAME recovered_nfl_main_menu_row_layout_semantics
             COMMAND $<TARGET_FILE:vc_nfl_main_menu_row_layout_tests>)
    set_tests_properties(
        recovered_nfl_main_menu_row_layout_semantics PROPERTIES
        PASS_REGULAR_EXPRESSION
            "NFL_MAIN_MENU_ROW_LAYOUT_NATIVE_PASS modes=3 cases=10")

    set(VC_NFL_FONT7_METRICS
        "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/fonts/font7.metrics.tsv")
    set(VC_NFL_FONT7_ATLAS
        "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/fonts/font7.png")
    set(VC_NFL_FONT7_REPORT
        "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_main_menu_font.json")
    set(VC_NFL_FORMATTED_TOKEN_REPORT
        "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_formatted_token.json")
    set(VC_NFL_FORMATTED_TOKEN_TSV
        "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_formatted_tokens.tsv")
    set(VC_NFL_TM_ICON
        "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/textures/outer_0003_8ee9eeed/0047_tm.png")

    if(EXISTS "${VC_NFL_FORMATTED_TOKEN_REPORT}" AND
       EXISTS "${VC_NFL_FORMATTED_TOKEN_TSV}" AND
       EXISTS "${VC_NFL_TM_ICON}")
        add_executable(vc_nfl_formatted_token_tests
            tests/nfl_formatted_token_test.c
            src/recovered/nfl2k5/formatted_token.c
        )
        target_include_directories(vc_nfl_formatted_token_tests PRIVATE include)
        target_link_libraries(vc_nfl_formatted_token_tests PRIVATE m)
        if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
            target_compile_options(vc_nfl_formatted_token_tests PRIVATE
                -Wall -Wextra -Wpedantic -Wconversion -Wshadow
                $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
            )
        endif()
        add_test(NAME recovered_nfl_formatted_token_semantics
            COMMAND $<TARGET_FILE:vc_nfl_formatted_token_tests>
                    "${VC_NFL_FORMATTED_TOKEN_TSV}")
        set_tests_properties(recovered_nfl_formatted_token_semantics PROPERTIES
            REQUIRED_FILES
                "${VC_NFL_FORMATTED_TOKEN_REPORT};${VC_NFL_FORMATTED_TOKEN_TSV};${VC_NFL_TM_ICON}"
            PASS_REGULAR_EXPRESSION
                "NFL_FORMATTED_TOKEN_NATIVE_PASS tokens=57 tm_index=40 tm_slot=9 tm_extent=25 casefold=ascii")
    endif()

    if(EXISTS "${VC_NFL_FONT7_METRICS}" AND
       EXISTS "${VC_NFL_FONT7_ATLAS}" AND
       EXISTS "${VC_NFL_FONT7_REPORT}")
        add_executable(vc_nfl_bitmap_font_tests
            tests/nfl_bitmap_font_test.c
            src/assets/bitmap_font_metrics.c
        )
        target_include_directories(vc_nfl_bitmap_font_tests PRIVATE include)
        target_link_libraries(vc_nfl_bitmap_font_tests PRIVATE m)
        if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
            target_compile_options(vc_nfl_bitmap_font_tests PRIVATE
                -Wall -Wextra -Wpedantic -Wconversion -Wshadow
                $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
            )
        endif()
        add_test(NAME recovered_nfl_bitmap_font_semantics
            COMMAND $<TARGET_FILE:vc_nfl_bitmap_font_tests>
                    "${VC_NFL_FONT7_METRICS}")
        set_tests_properties(recovered_nfl_bitmap_font_semantics PROPERTIES
            REQUIRED_FILES
                "${VC_NFL_FONT7_METRICS};${VC_NFL_FONT7_ATLAS};${VC_NFL_FONT7_REPORT}"
            PASS_REGULAR_EXPRESSION
                "NFL_BITMAP_FONT_NATIVE_PASS representation=recovered_host_representation glyphs=94 atlas=256x256 line=25 space=9 quick_game=177")
    endif()

    add_test(NAME host_cli_help
             COMMAND $<TARGET_FILE:vc_football_port> --help)
    set_tests_properties(host_cli_help PROPERTIES
        PASS_REGULAR_EXPRESSION "Usage:.*--assets.*--model.*--menu host")

    add_test(NAME host_cli_rejects_invalid_smoke
             COMMAND $<TARGET_FILE:vc_football_port> --smoke not-a-number)
    set_tests_properties(host_cli_rejects_invalid_smoke PROPERTIES
        WILL_FAIL TRUE)

    add_test(NAME host_cli_rejects_invalid_menu
             COMMAND $<TARGET_FILE:vc_football_port> --menu guest)
    set_tests_properties(host_cli_rejects_invalid_menu PROPERTIES
        WILL_FAIL TRUE)

    add_test(NAME host_cli_rejects_model_only_without_model
             COMMAND $<TARGET_FILE:vc_football_port> --model-only)
    set_tests_properties(host_cli_rejects_model_only_without_model PROPERTIES
        WILL_FAIL TRUE)

    set(VC_APF_PLAYER_SHADOW_DIR
        "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/apf2k8/skinned")
    set(VC_APF_PLAYER_SHADOW_STATIC
        "${VC_APF_PLAYER_SHADOW_DIR}/1310_0415_player_shadow_skin.gltf")
    set(VC_APF_PLAYER_SHADOW_STATIC_BIN
        "${VC_APF_PLAYER_SHADOW_DIR}/1310_0415_player_shadow_skin.bin")
    set(VC_APF_PLAYER_SHADOW_ANIMATED
        "${VC_APF_PLAYER_SHADOW_DIR}/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.gltf")
    set(VC_APF_PLAYER_SHADOW_ANIMATED_BIN
        "${VC_APF_PLAYER_SHADOW_DIR}/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.bin")
    set(VC_APF_PLAYER_SHADOW_REPORT
        "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/apf_player_shadow_gltf_export.json")
    if(EXISTS "${VC_APF_PLAYER_SHADOW_STATIC}" AND
       EXISTS "${VC_APF_PLAYER_SHADOW_STATIC_BIN}" AND
       EXISTS "${VC_APF_PLAYER_SHADOW_ANIMATED}" AND
       EXISTS "${VC_APF_PLAYER_SHADOW_ANIMATED_BIN}" AND
       EXISTS "${VC_APF_PLAYER_SHADOW_REPORT}")
        add_executable(vc_apf_player_shadow_runtime_tests
            tests/apf_player_shadow_runtime_test.c
            src/assets/model_animation.c
        )
        target_include_directories(
            vc_apf_player_shadow_runtime_tests PRIVATE include)
        target_link_libraries(vc_apf_player_shadow_runtime_tests PRIVATE
            assimp::assimp m)
        if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
            target_compile_options(vc_apf_player_shadow_runtime_tests PRIVATE
                -Wall -Wextra -Wpedantic -Wconversion -Wshadow
                $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
            )
        endif()
        add_test(NAME recovered_apf_player_shadow_host_semantics
            COMMAND $<TARGET_FILE:vc_apf_player_shadow_runtime_tests>
                    "${VC_APF_PLAYER_SHADOW_STATIC}"
                    "${VC_APF_PLAYER_SHADOW_ANIMATED}")
        set_tests_properties(
            recovered_apf_player_shadow_host_semantics PROPERTIES
            REQUIRED_FILES
                "${VC_APF_PLAYER_SHADOW_STATIC};${VC_APF_PLAYER_SHADOW_STATIC_BIN};${VC_APF_PLAYER_SHADOW_ANIMATED};${VC_APF_PLAYER_SHADOW_ANIMATED_BIN};${VC_APF_PLAYER_SHADOW_REPORT}"
            PASS_REGULAR_EXPRESSION
                "APF_PLAYER_SHADOW_RUNTIME_PASS static_vertices=175 animated_vertices=175 faces=306 bones=21 weights=181 channels=18 moved=175 max_delta=0.0449219383")
    endif()

    find_package(Python3 QUIET COMPONENTS Interpreter)
    if(Python3_Interpreter_FOUND)
        set(VC_ANIMATED_SKIN_FIXTURE
            "${CMAKE_CURRENT_BINARY_DIR}/fixtures/animated_skin.gltf")
        add_custom_command(
            OUTPUT "${VC_ANIMATED_SKIN_FIXTURE}"
            COMMAND ${Python3_EXECUTABLE}
                    ${CMAKE_CURRENT_SOURCE_DIR}/tools/create_animated_skin_fixture.py
                    --output "${VC_ANIMATED_SKIN_FIXTURE}"
            DEPENDS
                ${CMAKE_CURRENT_SOURCE_DIR}/tools/create_animated_skin_fixture.py
            VERBATIM)
        add_custom_target(vc_animated_skin_fixture ALL
            DEPENDS "${VC_ANIMATED_SKIN_FIXTURE}")

        add_executable(vc_model_animation_tests
            tests/model_animation_test.c
            src/assets/model_animation.c
        )
        target_include_directories(vc_model_animation_tests PRIVATE include)
        target_link_libraries(vc_model_animation_tests PRIVATE
            assimp::assimp m)
        add_dependencies(vc_model_animation_tests vc_animated_skin_fixture)
        if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
            target_compile_options(vc_model_animation_tests PRIVATE
                -Wall -Wextra -Wpedantic -Wconversion -Wshadow
                $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
            )
        endif()
        add_test(NAME host_model_animation_semantics
            COMMAND $<TARGET_FILE:vc_model_animation_tests>
                    "${VC_ANIMATED_SKIN_FIXTURE}")
        set_tests_properties(host_model_animation_semantics PROPERTIES
            PASS_REGULAR_EXPRESSION
                "MODEL_ANIMATION_RUNTIME_PASS bones=1 weights=3 delta=1")

        set(VC_NFL_REFEREE_ANIMATED_DIR
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/animated_samples")
        set(VC_NFL_REFEREE_ANIMATED_PROOF
            "${VC_NFL_REFEREE_ANIMATED_DIR}/0346_0109_referee_penalty_delay_game_R_120hz.gltf")
        set(VC_NFL_REFEREE_ANIMATED_BIN
            "${VC_NFL_REFEREE_ANIMATED_DIR}/0346_0109_referee_penalty_delay_game_R_120hz.bin")
        set(VC_NFL_REFEREE_ANIMATED_MANIFEST
            "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_referee_animated_gltf_manifest.json")
        set(VC_NFL_REFEREE_OWNERSHIP_REPORT
            "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_ref_clip_ownership.json")
        set(VC_NFL_REFEREE_ROOT_TRAJECTORY_REPORT
            "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_referee_root_trajectory.json")
        set(VC_NFL_REFEREE_RENDER_ROOT_REPORT
            "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_referee_render_root.json")
        if(EXISTS "${VC_NFL_REFEREE_ANIMATED_PROOF}" AND
           EXISTS "${VC_NFL_REFEREE_ANIMATED_BIN}" AND
           EXISTS "${VC_NFL_REFEREE_ANIMATED_MANIFEST}" AND
           EXISTS "${VC_NFL_REFEREE_OWNERSHIP_REPORT}" AND
           EXISTS "${VC_NFL_REFEREE_ROOT_TRAJECTORY_REPORT}" AND
           EXISTS "${VC_NFL_REFEREE_RENDER_ROOT_REPORT}")
            add_executable(vc_nfl_referee_animation_tests
                tests/nfl_referee_animation_runtime_test.c
                src/assets/model_animation.c
            )
            target_include_directories(
                vc_nfl_referee_animation_tests PRIVATE include)
            target_link_libraries(vc_nfl_referee_animation_tests PRIVATE
                assimp::assimp m)
            if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
                target_compile_options(vc_nfl_referee_animation_tests PRIVATE
                    -Wall -Wextra -Wpedantic -Wconversion -Wshadow
                    $<$<BOOL:${VC_PORT_STRICT}>:-Werror>
                )
            endif()
            add_test(NAME recovered_nfl_referee_animation_host_semantics
                COMMAND $<TARGET_FILE:vc_nfl_referee_animation_tests>
                        "${VC_NFL_REFEREE_ANIMATED_PROOF}")
            set_tests_properties(
                recovered_nfl_referee_animation_host_semantics PROPERTIES
                REQUIRED_FILES
                    "${VC_NFL_REFEREE_ANIMATED_PROOF};${VC_NFL_REFEREE_ANIMATED_BIN}"
                PASS_REGULAR_EXPRESSION
                    "NFL_REFEREE_ANIMATION_RUNTIME_PASS meshes=12 vertices=1375 bones=300 weights=2006 channels=50 moved=1375")

            add_test(NAME recovered_nfl_referee_animated_gltf_semantics
                COMMAND ${Python3_EXECUTABLE}
                        ${CMAKE_CURRENT_SOURCE_DIR}/tools/nfl_referee_animated_gltf_validate.py
                        --manifest
                            reports/assets/nfl_referee_animated_gltf_manifest.json
                        --asset-dir
                            assets/intermediate/nfl2k5/animated_samples
                        --ownership-report
                            reports/assets/nfl_ref_clip_ownership.json
                        --root-trajectory-report
                            reports/assets/nfl_referee_root_trajectory.json
                        --render-root-report
                            reports/assets/nfl_referee_render_root.json)
            set_tests_properties(
                recovered_nfl_referee_animated_gltf_semantics PROPERTIES
                WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
                REQUIRED_FILES
                    "${VC_NFL_REFEREE_ANIMATED_PROOF};${VC_NFL_REFEREE_ANIMATED_BIN};${VC_NFL_REFEREE_ANIMATED_MANIFEST};${VC_NFL_REFEREE_OWNERSHIP_REPORT};${VC_NFL_REFEREE_ROOT_TRAJECTORY_REPORT};${VC_NFL_REFEREE_RENDER_ROOT_REPORT}"
                PASS_REGULAR_EXPRESSION
                    "NFL_REFEREE_ANIMATED_GLTF_STRUCTURAL_PASS clip=ANM_REF_PENALTY_DELAY_OF_GAME_R keys=357 channels=25 targets=50")
        endif()

        set(VC_TEST_ASSET_ROOT "${CMAKE_CURRENT_BINARY_DIR}/test-assets")
        add_test(NAME host_generate_swapped_logo
            COMMAND ${Python3_EXECUTABLE}
                    ${CMAKE_CURRENT_SOURCE_DIR}/tools/create_placeholder_assets.py
                    --output ${VC_TEST_ASSET_ROOT}/ui/team_logo.png
                    --variant gold)
        set_tests_properties(host_generate_swapped_logo PROPERTIES
            FIXTURES_SETUP swapped_logo)
    endif()

    if(VC_PORT_ENABLE_GL_TESTS)
        add_test(NAME host_gl_smoke_default
            COMMAND $<TARGET_FILE:vc_football_port>
                    --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                    --smoke 3
                    --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-menu-default.png)
        set_tests_properties(host_gl_smoke_default PROPERTIES
            ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
            LABELS "gpu"
            FAIL_REGULAR_EXPRESSION "texture: .*not found;texture: could not load;model: could not load;audio clip: could not;audio clip: OpenAL is unavailable;audio clip: OpenAL upload failed;SMOKE FAIL"
            PASS_REGULAR_EXPRESSION "SMOKE PASS: rendered 3 frames")

        if(Python3_Interpreter_FOUND)
            add_test(NAME host_gl_smoke_swapped_logo
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${VC_TEST_ASSET_ROOT}
                        --smoke 3
                        --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-menu-swapped.png)
            set_tests_properties(host_gl_smoke_swapped_logo PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                FIXTURES_REQUIRED swapped_logo
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION "texture: .*not found;texture: could not load;model: could not load;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION "SMOKE PASS: rendered 3 frames")
        endif()

        add_test(NAME host_gl_smoke_recovered_nfl2k5_menu
            COMMAND $<TARGET_FILE:vc_football_port>
                    --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                    --menu nfl2k5
                    --smoke 3
                    --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl2k5.png)
        set_tests_properties(host_gl_smoke_recovered_nfl2k5_menu PROPERTIES
            ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
            FIXTURES_SETUP recovered_nfl2k5_menu_screenshot
            LABELS "gpu"
            FAIL_REGULAR_EXPRESSION "texture: .*not found;texture: could not load;model: could not load;audio clip: could not;audio clip: OpenAL is unavailable;audio clip: OpenAL upload failed;SMOKE FAIL"
            PASS_REGULAR_EXPRESSION "menu: nfl2k5 recovered host representation")

        if(EXISTS "${VC_NFL_FONT7_METRICS}" AND
           EXISTS "${VC_NFL_FONT7_ATLAS}" AND
           EXISTS "${VC_NFL_FONT7_REPORT}")
            add_test(NAME host_gl_smoke_recovered_nfl_font7
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --menu nfl2k5
                        --nfl-font-atlas "${VC_NFL_FONT7_ATLAS}"
                        --nfl-font-metrics "${VC_NFL_FONT7_METRICS}"
                        --nfl-tm-icon "${VC_NFL_TM_ICON}"
                        --smoke 3
                        --screenshot
                            ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl-font7.png)
            set_tests_properties(
                host_gl_smoke_recovered_nfl_font7 PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                REQUIRED_FILES
                    "${VC_NFL_FONT7_METRICS};${VC_NFL_FONT7_ATLAS};${VC_NFL_FONT7_REPORT};${VC_NFL_FORMATTED_TOKEN_REPORT};${VC_NFL_TM_ICON}"
                FIXTURES_SETUP recovered_nfl_font7_screenshot
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION
                    "bitmap font: metrics rejected;bitmap font: atlas load failed;bitmap font: NFL font7 loose assets unavailable;texture: .*not found;texture: could not load;model: could not load;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION
                    "bitmap font: loaded font7 recovered host representation(.|\n)*SMOKE PASS: rendered 3 frames")

            add_test(NAME host_gl_smoke_recovered_nfl_font7_literal_tm
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --menu nfl2k5
                        --nfl-font-atlas "${VC_NFL_FONT7_ATLAS}"
                        --nfl-font-metrics "${VC_NFL_FONT7_METRICS}"
                        --nfl-tm-icon
                            ${CMAKE_CURRENT_BINARY_DIR}/missing-nfl2k5-tm.png
                        --smoke 3
                        --screenshot
                            ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl-font7-literal-tm.png)
            set_tests_properties(
                host_gl_smoke_recovered_nfl_font7_literal_tm PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                REQUIRED_FILES
                    "${VC_NFL_FONT7_METRICS};${VC_NFL_FONT7_ATLAS};${VC_NFL_FORMATTED_TOKEN_REPORT}"
                FIXTURES_SETUP recovered_nfl_font7_literal_tm_screenshot
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION
                    "bitmap font: metrics rejected;bitmap font: atlas load failed;bitmap font: NFL font7 loose assets unavailable;texture: .*not found;texture: could not load;model: could not load;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION
                    "source markup remains visible(.|\n)*SMOKE PASS: rendered 3 frames")
        endif()

        add_test(NAME host_gl_smoke_recovered_apf2k8_menu
            COMMAND $<TARGET_FILE:vc_football_port>
                    --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                    --menu apf2k8
                    --smoke 3
                    --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-menu-apf2k8.png)
        set_tests_properties(host_gl_smoke_recovered_apf2k8_menu PROPERTIES
            ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
            FIXTURES_SETUP recovered_apf2k8_menu_screenshot
            LABELS "gpu"
            FAIL_REGULAR_EXPRESSION "texture: .*not found;texture: could not load;model: could not load;audio clip: could not;audio clip: OpenAL is unavailable;audio clip: OpenAL upload failed;SMOKE FAIL"
            PASS_REGULAR_EXPRESSION "menu: apf2k8 recovered host representation")

        if(Python3_Interpreter_FOUND)
            add_test(NAME host_gl_recovered_menu_screenshot_semantics
                COMMAND ${Python3_EXECUTABLE}
                        ${CMAKE_CURRENT_SOURCE_DIR}/tests/recovered_menu_screenshot_test.py
                        ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl2k5.png
                        ${CMAKE_CURRENT_BINARY_DIR}/host-menu-apf2k8.png)
            set_tests_properties(host_gl_recovered_menu_screenshot_semantics PROPERTIES
                FIXTURES_REQUIRED "recovered_nfl2k5_menu_screenshot;recovered_apf2k8_menu_screenshot"
                LABELS "gpu"
                PASS_REGULAR_EXPRESSION "RECOVERED_MENU_SCREENSHOTS_PASS")

            if(EXISTS "${VC_NFL_FONT7_METRICS}" AND
               EXISTS "${VC_NFL_FONT7_ATLAS}" AND
               EXISTS "${VC_NFL_FONT7_REPORT}")
                add_test(NAME host_gl_recovered_nfl_font7_screenshot_semantics
                    COMMAND ${Python3_EXECUTABLE}
                            ${CMAKE_CURRENT_SOURCE_DIR}/tests/nfl_bitmap_font_screenshot_test.py
                            ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl-font7.png
                            ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl2k5.png)
                set_tests_properties(
                    host_gl_recovered_nfl_font7_screenshot_semantics PROPERTIES
                    FIXTURES_REQUIRED
                        "recovered_nfl_font7_screenshot;recovered_nfl2k5_menu_screenshot"
                    LABELS "gpu"
                    PASS_REGULAR_EXPRESSION
                        "NFL_BITMAP_FONT_SCREENSHOT_PASS representation=recovered_host_representation")

                add_test(NAME host_gl_recovered_nfl_tm_screenshot_semantics
                    COMMAND ${Python3_EXECUTABLE}
                            ${CMAKE_CURRENT_SOURCE_DIR}/tests/nfl_formatted_token_screenshot_test.py
                            ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl-font7.png
                            ${CMAKE_CURRENT_BINARY_DIR}/host-menu-nfl-font7-literal-tm.png)
                set_tests_properties(
                    host_gl_recovered_nfl_tm_screenshot_semantics PROPERTIES
                    FIXTURES_REQUIRED
                        "recovered_nfl_font7_screenshot;recovered_nfl_font7_literal_tm_screenshot"
                    LABELS "gpu"
                    PASS_REGULAR_EXPRESSION
                        "NFL_FORMATTED_TOKEN_SCREENSHOT_PASS representation=recovered_host_representation token=TM index=40")
            endif()
        endif()

        set(VC_APF_COLLECTION_PROOF
            "${CMAKE_CURRENT_SOURCE_DIR}/reports/asset_samples/apf_scene/online_titlebar/0899_0021_online_titlebar.gltf")
        if(EXISTS "${VC_APF_COLLECTION_PROOF}")
            add_test(NAME host_gl_smoke_recovered_apf_collection
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model ${VC_APF_COLLECTION_PROOF}
                        --smoke 3
                        --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-apf-online-titlebar.png)
            set_tests_properties(host_gl_smoke_recovered_apf_collection PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION "model: could not load;model: could not upload;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION "model: loaded .*2 meshes,")
        endif()

        set(VC_NFL_STADIUM_COLLECTION_PROOF
            "${CMAKE_CURRENT_SOURCE_DIR}/reports/asset_samples/nfl_static_gltf/3161_0006_stadium.gltf")
        if(EXISTS "${VC_NFL_STADIUM_COLLECTION_PROOF}")
            add_test(NAME host_gl_smoke_recovered_nfl_stadium_collection
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model ${VC_NFL_STADIUM_COLLECTION_PROOF}
                        --smoke 3
                        --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-nfl-stadium-collection.png)
            set_tests_properties(host_gl_smoke_recovered_nfl_stadium_collection PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION "model: could not load;model: could not upload;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION "model: loaded .*562 meshes,")
        endif()

        set(VC_NFL_NORMSHORT3_COLLECTION_PROOF
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/models/0003_0051_geometry_font.gltf")
        if(EXISTS "${VC_NFL_NORMSHORT3_COLLECTION_PROOF}")
            add_test(NAME host_gl_smoke_recovered_nfl_normshort3_collection
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model ${VC_NFL_NORMSHORT3_COLLECTION_PROOF}
                        --smoke 3
                        --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-nfl-geometry-font.png)
            set_tests_properties(host_gl_smoke_recovered_nfl_normshort3_collection PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION "model: could not load;model: could not upload;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION "model: uploaded 973 vertices and 7521 triangle indices")
        endif()

        set(VC_NFL_RAW_SKIN_PROOF
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/raw_skin_samples/0003_0113_lo_body_raw_skin.gltf")
        if(EXISTS "${VC_NFL_RAW_SKIN_PROOF}")
            add_test(NAME host_gl_smoke_recovered_nfl_raw_skin
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model ${VC_NFL_RAW_SKIN_PROOF}
                        --smoke 3
                        --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-nfl-raw-skin.png)
            set_tests_properties(host_gl_smoke_recovered_nfl_raw_skin PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION "model: could not load;model: could not upload;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION "model: uploaded 3690 vertices and 36267 triangle indices")
        endif()

        set(VC_NFL_METER_SKIN_PROOF
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/meter_skin_samples/0003_0113_lo_body_meter_skin.gltf")
        if(EXISTS "${VC_NFL_METER_SKIN_PROOF}")
            add_test(NAME host_gl_smoke_recovered_nfl_meter_skin
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model ${VC_NFL_METER_SKIN_PROOF}
                        --smoke 3
                        --screenshot ${CMAKE_CURRENT_BINARY_DIR}/host-nfl-meter-skin.png)
            set_tests_properties(host_gl_smoke_recovered_nfl_meter_skin PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION "model: could not load;model: could not upload;model: could not prepare;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION "model: CPU scene evaluator ready \\(2775 bones, 7522 weights, 0 animations\\)")
        endif()

        set(VC_NFL_HI_BODY_SKIN_PROOF
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.gltf")
        set(VC_NFL_HI_BODY_SKIN_BIN
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/intermediate/nfl2k5/hi_body_skin/0003_0114_hi_body_meter_skin.bin")
        set(VC_NFL_HI_BODY_SKIN_REPORT
            "${CMAKE_CURRENT_SOURCE_DIR}/reports/assets/nfl_hi_body_skin.json")
        if(EXISTS "${VC_NFL_HI_BODY_SKIN_PROOF}" AND
           EXISTS "${VC_NFL_HI_BODY_SKIN_BIN}" AND
           EXISTS "${VC_NFL_HI_BODY_SKIN_REPORT}")
            add_test(NAME host_gl_smoke_recovered_nfl_hi_body_skin
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model ${VC_NFL_HI_BODY_SKIN_PROOF}
                        --smoke 3
                        --screenshot
                            ${CMAKE_CURRENT_BINARY_DIR}/host-nfl-hi-body-skin.png)
            set_tests_properties(
                host_gl_smoke_recovered_nfl_hi_body_skin PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                REQUIRED_FILES
                    "${VC_NFL_HI_BODY_SKIN_PROOF};${VC_NFL_HI_BODY_SKIN_BIN};${VC_NFL_HI_BODY_SKIN_REPORT}"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION
                    "model: could not load;model: could not upload;model: could not prepare;model: no bounded triangle geometry;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION
                    "model: CPU scene evaluator ready \\(5332 bones, 12726 weights, 0 animations\\)(.|\n)*SMOKE PASS: rendered 3 frames")
        endif()

        if(Python3_Interpreter_FOUND)
            add_test(NAME host_gl_smoke_animated_skin_fixture
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model "${VC_ANIMATED_SKIN_FIXTURE}"
                        --smoke 31
                        --screenshot
                            ${CMAKE_CURRENT_BINARY_DIR}/host-animated-skin.png)
            set_tests_properties(host_gl_smoke_animated_skin_fixture PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION
                    "model: could not load;model: could not prepare;animated CPU skinning update failed;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION
                    "model: CPU scene evaluator ready \\(1 bones, 3 weights, 1 animations\\)")
        endif()

        if(EXISTS "${VC_NFL_REFEREE_ANIMATED_PROOF}" AND
           EXISTS "${VC_NFL_REFEREE_ANIMATED_BIN}")
            add_test(NAME host_gl_smoke_recovered_nfl_referee_animation
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model "${VC_NFL_REFEREE_ANIMATED_PROOF}"
                        --smoke 91
                        --screenshot
                            ${CMAKE_CURRENT_BINARY_DIR}/host-nfl-referee-animation.png)
            set_tests_properties(
                host_gl_smoke_recovered_nfl_referee_animation PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                REQUIRED_FILES
                    "${VC_NFL_REFEREE_ANIMATED_PROOF};${VC_NFL_REFEREE_ANIMATED_BIN}"
                LABELS "gpu"
                FAIL_REGULAR_EXPRESSION
                    "model: could not load;model: could not upload;model: could not prepare;model: animated CPU skinning update failed;model: no bounded triangle geometry;texture: .*not found;texture: could not load;audio clip: could not;audio clip: OpenAL is unavailable;audio clip: OpenAL upload failed;screenshot: could not write;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION
                    "model: CPU scene evaluator ready \\(300 bones, 2006 weights, 1 animations\\)(.|\n)*SMOKE PASS: rendered 91 frames")
        endif()

        if(EXISTS "${VC_APF_PLAYER_SHADOW_STATIC}" AND
           EXISTS "${VC_APF_PLAYER_SHADOW_STATIC_BIN}" AND
           EXISTS "${VC_APF_PLAYER_SHADOW_ANIMATED}" AND
           EXISTS "${VC_APF_PLAYER_SHADOW_ANIMATED_BIN}" AND
           EXISTS "${VC_APF_PLAYER_SHADOW_REPORT}")
            add_test(NAME host_gl_smoke_recovered_apf_player_shadow_static
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model "${VC_APF_PLAYER_SHADOW_STATIC}"
                        --smoke 3
                        --screenshot
                            ${CMAKE_CURRENT_BINARY_DIR}/host-apf-player-shadow-static.png)
            set_tests_properties(
                host_gl_smoke_recovered_apf_player_shadow_static PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                REQUIRED_FILES
                    "${VC_APF_PLAYER_SHADOW_STATIC};${VC_APF_PLAYER_SHADOW_STATIC_BIN};${VC_APF_PLAYER_SHADOW_REPORT}"
                FIXTURES_SETUP apf_player_shadow_static_screenshot
                LABELS "gpu;apf_player_shadow"
                FAIL_REGULAR_EXPRESSION
                    "model: could not load;model: could not upload;model: could not prepare;model: no bounded triangle geometry;texture: .*not found;texture: could not load;audio clip: could not;audio clip: OpenAL is unavailable;audio clip: OpenAL upload failed;screenshot: could not write;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION
                    "model: uploaded 175 vertices and 918 triangle indices(.|\n)*model: CPU scene evaluator ready \\(21 bones, 181 weights, 0 animations\\)(.|\n)*SMOKE PASS: rendered 3 frames")

            add_test(NAME host_gl_smoke_recovered_apf_player_shadow_animation
                COMMAND $<TARGET_FILE:vc_football_port>
                        --assets ${CMAKE_CURRENT_SOURCE_DIR}/assets/mod/common
                        --model "${VC_APF_PLAYER_SHADOW_ANIMATED}"
                        --smoke 2
                        --screenshot
                            ${CMAKE_CURRENT_BINARY_DIR}/host-apf-player-shadow-animated.png)
            set_tests_properties(
                host_gl_smoke_recovered_apf_player_shadow_animation PROPERTIES
                ENVIRONMENT "SDL_AUDIODRIVER=dummy;ALSOFT_DRIVERS=null"
                REQUIRED_FILES
                    "${VC_APF_PLAYER_SHADOW_ANIMATED};${VC_APF_PLAYER_SHADOW_ANIMATED_BIN};${VC_APF_PLAYER_SHADOW_REPORT}"
                FIXTURES_SETUP apf_player_shadow_animated_screenshot
                LABELS "gpu;apf_player_shadow"
                FAIL_REGULAR_EXPRESSION
                    "model: could not load;model: could not upload;model: could not prepare;model: animated CPU skinning update failed;model: no bounded triangle geometry;texture: .*not found;texture: could not load;audio clip: could not;audio clip: OpenAL is unavailable;audio clip: OpenAL upload failed;screenshot: could not write;SMOKE FAIL"
                PASS_REGULAR_EXPRESSION
                    "model: uploaded 175 vertices and 918 triangle indices(.|\n)*model: CPU scene evaluator ready \\(21 bones, 181 weights, 1 animations\\)(.|\n)*SMOKE PASS: rendered 2 frames")

            if(Python3_Interpreter_FOUND)
                add_test(
                    NAME host_gl_recovered_apf_player_shadow_screenshot_semantics
                    COMMAND ${Python3_EXECUTABLE}
                            ${CMAKE_CURRENT_SOURCE_DIR}/tests/apf_player_shadow_screenshot_test.py
                            ${CMAKE_CURRENT_BINARY_DIR}/host-apf-player-shadow-static.png
                            ${CMAKE_CURRENT_BINARY_DIR}/host-apf-player-shadow-animated.png)
                set_tests_properties(
                    host_gl_recovered_apf_player_shadow_screenshot_semantics
                    PROPERTIES
                    FIXTURES_REQUIRED
                        "apf_player_shadow_static_screenshot;apf_player_shadow_animated_screenshot"
                    LABELS "gpu;apf_player_shadow"
                    PASS_REGULAR_EXPRESSION
                        "APF_PLAYER_SHADOW_SCREENSHOTS_PASS dimensions=1280x720")
            endif()
        endif()
    endif()
endif()
