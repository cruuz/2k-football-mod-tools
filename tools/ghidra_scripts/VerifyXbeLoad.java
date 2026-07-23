// Verify that the XboxDev XBE loader created an executable .text block and entry function.
// @category Xbox

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.mem.MemoryBlock;

public class VerifyXbeLoad extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!"Xbox Executable Format (XBE)".equals(currentProgram.getExecutableFormat())) {
            throw new IllegalStateException(
                "wrong executable format: " + currentProgram.getExecutableFormat());
        }

        MemoryBlock text = currentProgram.getMemory().getBlock(".text");
        if (text == null || !text.isExecute()) {
            throw new IllegalStateException("missing executable .text block");
        }

        Function entry = null;
        FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
        while (functions.hasNext()) {
            Function candidate = functions.next();
            if ("entry".equals(candidate.getName())) {
                entry = candidate;
                break;
            }
        }
        if (entry == null) {
            throw new IllegalStateException("loader did not create the entry function");
        }

        DecompInterface decompiler = new DecompInterface();
        try {
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open the program");
            }
            DecompileResults results = decompiler.decompileFunction(entry, 30, monitor);
            if (!results.decompileCompleted() || results.getDecompiledFunction() == null) {
                throw new IllegalStateException(
                    "entry decompilation failed: " + results.getErrorMessage());
            }
            println("XBE_LOADER_TEST_PASS");
            println("format=" + currentProgram.getExecutableFormat());
            println("language=" + currentProgram.getLanguageID());
            println("image_base=" + currentProgram.getImageBase());
            println("text=" + text.getStart() + "-" + text.getEnd());
            println("entry=" + entry.getEntryPoint());
            println(results.getDecompiledFunction().getC());
        }
        finally {
            decompiler.dispose();
        }
    }
}
