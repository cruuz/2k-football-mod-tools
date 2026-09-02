// Find the code that composites a team crest onto the helmet surface.
//
// The crest is not sampled by the helmet material -- the helmet shader declares
// BaseSampler, BumpSampler, GroundShadowSampler and SpecularLightmapSampler and
// no logo sampler at all -- so the logo must be written into the helmet's
// runtime surface by game code. The rectangle it is written into is the "box"
// every modder hits: the logo can be any art you like but never larger or
// elsewhere.
//
// This locates the UTF-16BE resource-name templates the logo path uses
// ("{0:D2}_logo_l0", "uniform_logocache.iff", "LOGOS") and reports every
// function that references them, so the compositing routine can be read rather
// than guessed at.
//
// @category APF

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class ApfCrestBlitTrace extends GhidraScript {

    private static final String[] TARGETS = {
        "{0:D2}_logo_l0",
        "{0:D2}_logo_l1",
        "uniform_logocache.iff",
        "LOGOS",
        "logo_0%s_0",
    };

    @Override
    public void run() throws Exception {
        Memory memory = currentProgram.getMemory();
        println("APF crest blit trace over " + currentProgram.getName());

        for (String target : TARGETS) {
            byte[] needle = target.getBytes(StandardCharsets.UTF_16BE);
            List<Address> found = new ArrayList<>();
            Address at = memory.findBytes(
                memory.getMinAddress(), needle, null, true, monitor);
            while (at != null) {
                found.add(at);
                Address next = at.add(2);
                at = memory.findBytes(next, needle, null, true, monitor);
                if (found.size() > 16) {
                    break;
                }
            }
            println("");
            println("=== " + target + " : " + found.size() + " occurrence(s)");
            for (Address site : found) {
                println("  string @ " + site);
                Set<String> owners = new LinkedHashSet<>();
                ReferenceIterator refs =
                    currentProgram.getReferenceManager().getReferencesTo(site);
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Address from = ref.getFromAddress();
                    Function owner = getFunctionContaining(from);
                    owners.add(owner == null
                        ? "  ref from " + from + " (no function)"
                        : "  ref from " + from + " in " + owner.getName()
                          + " @" + owner.getEntryPoint());
                }
                if (owners.isEmpty()) {
                    // Xbox 360 code loads addresses with lis/ori pairs, which
                    // Ghidra does not always turn into a reference; report the
                    // raw halves so they can be searched for by hand.
                    long offset = site.getOffset();
                    println(String.format(
                        "    no direct refs; lis=0x%04x ori=0x%04x",
                        (offset >>> 16) & 0xFFFF, offset & 0xFFFF));
                } else {
                    for (String owner : owners) {
                        println("  " + owner);
                    }
                }
            }
        }
        println("");
        println("APF crest blit trace complete");
    }
}
