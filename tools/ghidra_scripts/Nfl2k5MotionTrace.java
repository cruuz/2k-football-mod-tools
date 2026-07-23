// Emit focused static evidence for NFL 2K5 SMCD/MMCD motion resources.
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

public class Nfl2k5MotionTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00168290L, 0x00168300L, 0x00168360L, 0x001683D0L,
        0x00168400L, 0x00168430L, 0x00168440L, 0x00168470L,
        0x00168480L, 0x001684D0L,
        0x00168520L, 0x00168580L, 0x001685B0L, 0x001685E0L,
        0x00168660L, 0x001686C0L, 0x00168740L, 0x00168750L,
        0x001687B0L, 0x001687C0L, 0x001687E0L,
        0x002D0180L, 0x002D01D0L, 0x002D0240L, 0x002D0280L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private void writeInstructions(BufferedWriter output, long first, long afterLast)
            throws Exception {
        Address cursor = address(first);
        Address limit = address(afterLast);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(cursor.getUnsignedOffset()) + " <no instruction>\n");
                cursor = cursor.add(1);
            }
            else {
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(cursor);
                output.write(hex(cursor.getUnsignedOffset()) + " " + instruction +
                    " owner=" + functionName(owner) + " refs=" +
                    String.join(";", referencesTo(cursor)) + "\n");
                cursor = instruction.getMaxAddress().add(1);
            }
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: Nfl2k5MotionTrace.java OUTPUT_DIRECTORY");
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
        List<Long> missingFunctions = new ArrayList<>();
        File traceFile = new File(directory, "motion_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 SMCD/MMCD focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");
            trace.write("REGISTRY_AND_CALLBACK_WINDOW\n");
            writeInstructions(trace, 0x00168260L, 0x00168580L);
            trace.write("\nLOOKUP_AND_CONSUMER_WINDOW\n");
            writeInstructions(trace, 0x001685B0L, 0x00168850L);
            trace.write("\nMOTION_ROOT_RELOCATORS\n");
            writeInstructions(trace, 0x002D0180L, 0x002D02C0L);
            trace.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                trace.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
                if (function != null) functions.add(function);
                else missingFunctions.add(value);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "motion_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* NFL 2K5 SMCD/MMCD focused pseudo-C. */\n\n");
            for (long value : missingFunctions) {
                pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                    "; Ghidra has no saved function boundary; exact instructions are " +
                    "retained in motion_trace.txt.\n");
            }
            if (!missingFunctions.isEmpty()) pseudo.write("\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 60 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL2K5_MOTION_TRACE_COMPLETE functions=" + functions.size());
    }
}
