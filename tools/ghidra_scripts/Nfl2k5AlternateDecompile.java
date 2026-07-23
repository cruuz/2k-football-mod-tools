// Try less expensive decompiler analysis passes for an NFL 2K5 hard function.
// This is a read-only recovery aid; output records every option/style used.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class Nfl2k5AlternateDecompile extends GhidraScript {
    private String addr(Address address) {
        return String.format("0x%08X", address.getUnsignedOffset());
    }

    private boolean attempt(BufferedWriter writer, Function function, String label, String style,
            boolean loops, boolean predicate, boolean splitStructures, int timeout) throws Exception {
        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        options.grabFromProgram(currentProgram);
        options.setAnalyzeForLoops(loops);
        options.setPredicate(predicate);
        options.setSplitStructures(splitStructures);
        options.setDefaultTimeout(timeout);
        decompiler.setOptions(options);
        decompiler.setSimplificationStyle(style);
        if (!decompiler.openProgram(currentProgram)) {
            writer.write("/* attempt=" + label + " open_failed */\n\n");
            decompiler.dispose();
            return false;
        }
        long started = System.nanoTime();
        DecompileResults result = decompiler.decompileFunction(function, timeout, monitor);
        double seconds = (System.nanoTime() - started) / 1_000_000_000.0;
        writer.write("/* attempt=" + label + " style=" + style + " loops=" + loops +
            " predicate=" + predicate + " split_structures=" + splitStructures +
            " timeout=" + timeout + " elapsed=" + String.format("%.6f", seconds) +
            " completed=" + result.decompileCompleted() + " timed_out=" + result.isTimedOut() +
            " error=" + result.getErrorMessage().replace('\n', ' ').replace('\r', ' ') + " */\n");
        if (result.getDecompiledFunction() != null) {
            writer.write(result.getDecompiledFunction().getC());
        }
        else {
            writer.write("// PORTME: this alternate pass did not produce C.\n");
        }
        writer.write("\n");
        boolean success = result.decompileCompleted() && result.getDecompiledFunction() != null;
        decompiler.dispose();
        return success;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "usage: Nfl2k5AlternateDecompile.java OUTPUT_FILE ADDRESS TIMEOUT_SECONDS");
        }
        File output = new File(args[0]);
        File parent = output.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }
        Address requested = toAddr(Long.decode(args[1]));
        int timeout = Integer.parseInt(args[2]);
        Function function = currentProgram.getFunctionManager().getFunctionAt(requested);
        if (function == null) function = currentProgram.getFunctionManager().getFunctionContaining(requested);
        if (function == null) throw new IllegalArgumentException("no function at " + requested);

        try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
            writer.write("/* NFL 2K5 alternate decompiler recovery\n");
            writer.write(" * function=" + addr(function.getEntryPoint()) + ":" + function.getName() + "\n */\n\n");
            boolean success = attempt(writer, function, "decompile_no_expensive_passes", "decompile",
                false, false, false, timeout);
            if (!success) success = attempt(writer, function, "normalize", "normalize",
                false, false, false, timeout);
            if (!success) success = attempt(writer, function, "register", "register",
                false, false, false, timeout);
            if (!success) attempt(writer, function, "firstpass", "firstpass",
                false, false, false, timeout);
        }
        println("NFL2K5_ALTERNATE_DECOMPILE_COMPLETE output=" + output);
    }
}
