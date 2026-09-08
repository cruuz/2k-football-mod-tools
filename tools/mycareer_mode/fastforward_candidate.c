/* Capacity lower bound only. NEVER installed or executed.
 * This lacks scene/timestep, pause, audio, animation, interruption and live
 * resume handling. It is not a working Supersim or an approved frame loop.
 * Appended to runtime.c only by measure_mode4.py to measure these bytes.
 */
u32 m4_fastforward_candidate(void) {
    u32 frames=0;
    if(!inline_active()) return 0;
    while(frames<600 && !mode_unit_present() && G(0xA83A18)==3) {
        CALL0(0x11a7c0);
        frames++;
    }
    return frames;
}
