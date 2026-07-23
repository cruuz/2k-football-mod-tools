#include "ppc_config.h"
#include "ppc_context.h"

#include <array>
#include <cassert>
#include <cstdint>
#include <csignal>
#include <cstdio>
#include <sys/wait.h>
#include <unistd.h>

namespace {

struct CacheStoreObservation
{
    uint8_t* base{};
    uint32_t effectiveAddress{};
    uint32_t cacheLineAddress{};
    uint32_t cacheLineSize{};
    uint32_t callCount{};
};

CacheStoreObservation observation;

void RecordCacheStore(
    uint8_t* base,
    uint32_t effectiveAddress,
    uint32_t cacheLineAddress,
    uint32_t cacheLineSize)
{
    observation = {
        base,
        effectiveAddress,
        cacheLineAddress,
        cacheLineSize,
        observation.callCount + 1,
    };
}

int RunAndExpectAbort(uint8_t* base, uint32_t cacheLineSize)
{
    const pid_t child = fork();
    assert(child >= 0);
    if (child == 0)
    {
        PPCDispatchDataCacheStore(base, 0x12345, cacheLineSize);
        _exit(99);
    }

    int status = 0;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFSIGNALED(status));
    assert(WTERMSIG(status) == SIGABRT);
    return WTERMSIG(status);
}

} // namespace

int main()
{
    alignas(128) std::array<uint8_t, 512> guestMemory{};
    uint8_t* base = guestMemory.data();
    PPCSetDataCacheStoreHook(&RecordCacheStore);

    // APF's nonzero-RA form computes uint32(RA + RB), including wraparound.
    const uint32_t ra = 0xFFFFFFC0u;
    const uint32_t rb = 0x00000185u;
    PPC_DATA_CACHE_BLOCK_STORE((ra + rb), 128);
    assert(observation.base == base);
    assert(observation.effectiveAddress == 0x00000145u);
    assert(observation.cacheLineAddress == 0x00000100u);
    assert(observation.cacheLineSize == 128);
    assert(observation.callCount == 1);

    // RA=0 uses RB directly, and the hook receives the block containing EA.
    const uint32_t rbOnly = 0x00ABCDEFu;
    PPC_DATA_CACHE_BLOCK_STORE((rbOnly), 128);
    assert(observation.effectiveAddress == rbOnly);
    assert(observation.cacheLineAddress == 0x00ABCD80u);
    assert(observation.cacheLineSize == 128);
    assert(observation.callCount == 2);

    PPCSetDataCacheStoreHook(nullptr);
    const int defaultHookSignal = RunAndExpectAbort(base, 128);

    PPCSetDataCacheStoreHook(&RecordCacheStore);
    const int invalidSizeSignal = RunAndExpectAbort(base, 64);
    std::printf(
        "APF_DCBST_HOOK_TEST_PASS nonzero_ra_ea=0x%08X "
        "nonzero_ra_line=0x%08X rb_only_ea=0x%08X "
        "rb_only_line=0x%08X line_size=128 default_signal=%d "
        "invalid_size_signal=%d\n",
        0x00000145u,
        0x00000100u,
        rbOnly,
        0x00ABCD80u,
        defaultHookSignal,
        invalidSizeSignal);
    return 0;
}
