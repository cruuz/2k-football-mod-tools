// Read the code that loads a team crest, so the rectangle it composites into
// can be found.
//
// ApfCrestBlitTrace located the resource-name templates and two functions that
// reference them. Two of the templates ("{0:D2}_logo_l0", "logo_0%s_0") had no
// Ghidra reference at all, because Xbox 360 code materialises an address with a
// lis/ori pair rather than a relocation, and the analyser does not always fold
// those into a reference.
//
// This does two things: it scans the whole text for lis/ori pairs that build the
// known string addresses and reports the owning functions, and it decompiles
// every function implicated so the compositing path can be read directly.
//
// @category APF

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;

import java.util.LinkedHashSet;
import java.util.Set;

public class ApfCrestBlitDecomp extends GhidraScript {

    // The crest resource-name templates, from ApfCrestBlitTrace.
    private static final long[] TARGETS = {
        0x845030c8L,   // {0:D2}_logo_l0
        0x845030e8L,   // {0:D2}_logo_l1
        0x845022e4L,   // uniform_logocache.iff
        0x84503094L,   // logo_0%s_0
        0x845030bcL,   // LOGOS
    };

    // Functions ApfCrestBlitTrace already tied to those strings.
    private static final long[] KNOWN = { 0x8467c978L, 0x84688690L };

    @Override
    public void run() throws Exception {
        Set<Function> interesting = new LinkedHashSet<>();

        println("Scanning for lis/ori pairs that build the crest string addresses");
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        Instruction previous = null;
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction current = it.next();
            if (previous != null) {
                Long built = builtAddress(previous, current);
                if (built != null) {
                    for (long target : TARGETS) {
                        if (built.longValue() == target) {
                            Function owner = getFunctionContaining(current.getAddress());
                            println(String.format(
                                "  0x%08x built at %s in %s",
                                target, current.getAddress(),
                                owner == null ? "(no function)" : owner.getName()));
                            if (owner != null) {
                                interesting.add(owner);
                            }
                        }
                    }
                }
            }
            previous = current;
        }

        for (long entry : KNOWN) {
            Function fn = getFunctionAt(toAddr(entry));
            if (fn != null) {
                interesting.add(fn);
            }
        }

        println("");
        println("Decompiling " + interesting.size() + " implicated function(s)");
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            for (Function fn : interesting) {
                println("");
                println("======== " + fn.getName() + " @ " + fn.getEntryPoint());
                DecompileResults results = decompiler.decompileFunction(fn, 120, monitor);
                if (results != null && results.decompileCompleted()) {
                    println(results.getDecompiledFunction().getC());
                } else {
                    println("  (decompilation failed: "
                        + (results == null ? "no result" : results.getErrorMessage()) + ")");
                }
            }
        } finally {
            decompiler.dispose();
        }
        println("APF crest blit decomp complete");
    }

    /** If these two instructions are a lis/ori (or lis/addi) pair, the address they build. */
    private Long builtAddress(Instruction hi, Instruction lo) {
        String hiOp = hi.getMnemonicString();
        String loOp = lo.getMnemonicString();
        boolean hiIsLis = hiOp.equals("lis") || hiOp.equals("addis");
        boolean loIsLow = loOp.equals("ori") || loOp.equals("addi");
        if (!hiIsLis || !loIsLow) {
            return null;
        }
        Scalar hiValue = scalarOf(hi);
        Scalar loValue = scalarOf(lo);
        if (hiValue == null || loValue == null) {
            return null;
        }
        long high = hiValue.getUnsignedValue() & 0xFFFFL;
        long low = loOp.equals("addi")
            ? (loValue.getSignedValue() & 0xFFFFL)
            : (loValue.getUnsignedValue() & 0xFFFFL);
        long combined = (high << 16);
        combined += loOp.equals("addi") ? loValue.getSignedValue() : low;
        return combined & 0xFFFFFFFFL;
    }

    private Scalar scalarOf(Instruction instruction) {
        for (int i = instruction.getNumOperands() - 1; i >= 0; i--) {
            Object[] objects = instruction.getOpObjects(i);
            for (Object object : objects) {
                if (object instanceof Scalar) {
                    return (Scalar) object;
                }
            }
        }
        return null;
    }
}
