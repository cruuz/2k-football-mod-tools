// Emit focused NFL 2K5 gameplay-referee transform-to-render evidence.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflRefereeRenderRootTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00021860L, 0x00021900L, 0x00021930L,
        0x00022C00L, 0x000233C0L, 0x000243D0L,
        0x00037EB0L,
        0x00054E20L, 0x0005C530L, 0x00064E80L, 0x00074DD0L,
        0x00096350L, 0x00096600L, 0x00096A80L, 0x00096AD0L,
        0x00096B00L, 0x00096B20L,
        0x00096B50L, 0x00096B90L,
        0x00111E00L, 0x0011A540L, 0x0011A7C0L, 0x0011A8F0L,
        0x001D2D90L,
        0x00217D00L, 0x00217EB0L, 0x00218010L, 0x002180D0L,
        0x0028EA10L, 0x0028ECF0L, 0x002CC570L, 0x003CA3D0L
    };

    private static final long[] TARGETS = {
        0x00021860L, 0x00021900L, 0x00021930L,
        0x00022C00L, 0x000233C0L, 0x000243D0L, 0x00037EB0L,
        0x00074DD0L, 0x00096B20L, 0x00096B50L, 0x00096B90L,
        0x0011A8F0L, 0x001D2D90L, 0x00218010L, 0x002180D0L,
        0x002CC570L, 0x003CA3D0L,
        0x00B66120L, 0x00B661C0L, 0x00B661C4L,
        0x00B661CCL, 0x00B661D0L, 0x00E60274L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace()
            .getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String functionName(Function function) {
        return function == null ? "none" :
            hex(function.getEntryPoint().getUnsignedOffset()) + ":" +
            function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator =
            currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager()
                .getFunctionContaining(reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) +
                "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private void writeFunctionInstructions(BufferedWriter output,
            Function function) throws Exception {
        Instruction instruction = currentProgram.getListing()
            .getInstructionAt(function.getEntryPoint());
        while (instruction != null &&
               function.getBody().contains(instruction.getAddress())) {
            output.write(hex(instruction.getAddress().getUnsignedOffset()) +
                " " + instruction + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) +
                "\n");
            instruction = instruction.getNext();
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflRefereeRenderRootTrace.java OUTPUT_DIRECTORY");
        }
        if (!"444064a9ec984dd29d2c05a43f5c96e8".equalsIgnoreCase(
                currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable MD5 " +
                currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> functions = new LinkedHashSet<>();
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(
                new File(directory,
                    "nfl_referee_render_root_trace.txt")))) {
            trace.write("NFL 2K5 gameplay-referee transform-to-render focused trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() +
                "\n\nKEY_REFERENCES\n");
            for (long target : TARGETS) {
                trace.write(hex(target) + " refs=" +
                    String.join(";", referencesTo(address(target))) + "\n");
            }
            trace.write("\nFOCUSED_FUNCTION_REFERENCES\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                trace.write(hex(value) + " " + functionName(function) +
                    " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
                if (function == null) {
                    throw new IllegalStateException(
                        "missing focused function boundary at " + hex(value));
                }
                functions.add(function);
            }
            trace.write("\nFOCUSED_INSTRUCTIONS\n");
            for (Function function : functions) {
                trace.write("\nFUNCTION " + functionName(function) + "\n");
                writeFunctionInstructions(trace, function);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory,
                    "nfl_referee_render_root_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 gameplay-referee transform-to-render focused pseudo-C. */\n\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result =
                    decompiler.decompileFunction(function, 240, monitor);
                if (result.decompileCompleted() &&
                    result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ?
                        "timed out after 240 seconds" : result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        hex(value) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
            pseudo.write("// PORTME: preserve the per-frame gameplay referee actor index and visibility registration when translating this chain.\n");
            pseudo.write("// PORTME: do not collapse actor transform, external root, current matrix array, render-object matrix pointer, and skin palette into one address space.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_REFEREE_RENDER_ROOT_TRACE_COMPLETE functions=" +
            functions.size());
    }
}
