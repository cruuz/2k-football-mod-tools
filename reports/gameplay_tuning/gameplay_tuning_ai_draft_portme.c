/* Auto-generated evidence placeholders; no original game code is included. */
#include <stddef.h>

typedef struct vc_portme_item {
    const char *game;
    const char *address;
    const char *work;
} vc_portme_item;

static const vc_portme_item vc_gameplay_portme[] = {
    /* PORTME: identify the final NFL catch-success/drop consumer and prove slider polarity. */
    {"NFL 2K5", "0x00E600F4/0x00E60118", "trace Human/CPU Catching from globals to final outcome branch"},
    /* PORTME: prove safety before exposing values outside the stock 0..1 interval. */
    {"NFL 2K5", "0x000E3B90", "trace every indexed slider consumer and validate finite ranges"},
    /* PORTME: map the Xbox save/profile container, integrity fields, and precedence. */
    {"NFL 2K5", "0x000E3DC0", "locate serialized slider payload without reusing disc offsets"},
    /* PORTME: runtime-test an emulator-compatible copied-XBE patch; never overwrite retail input. */
    {"NFL 2K5", "0x00589588", "validate CPU draft weight changes and section-digest/signature handling"},
    /* PORTME: identify the final APF catch-success/drop consumer and prove slider polarity. */
    {"APF 2K8", "0x84F3FC44/0x84F3FC20", "resolve indexed/computed reads after runtime synchronization"},
    /* PORTME: prove downstream safety for APF profile values outside 0..1. */
    {"APF 2K8", "0x8470A630", "trace all 21 imported floats through final gameplay consumers"},
    /* PORTME: map APF profile container/integrity and offline-versus-online precedence. */
    {"APF 2K8", "0x8471F2A0", "recover exact serialized owner of the 0x54-byte slider vector"},
    /* PORTME: resolve TOC/computed ownership or prove the retained draft table is dead data. */
    {"APF 2K8", "0x820F4B70", "find a CPU draft selector before offering any APF draft-AI control"},
    /* PORTME: franchise transfer needs subsystem integration, not an asset copy. */
    {"cross-title", "unresolved", "map mode state, season DB, schedule, contracts, UI, and saves"},
};

size_t vc_gameplay_portme_count(void) {
    return sizeof(vc_gameplay_portme) / sizeof(vc_gameplay_portme[0]);
}
