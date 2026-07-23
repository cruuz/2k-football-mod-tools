// Emit focused NFL 2K5 rest-orientation and current-matrix evidence.
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

public class NflRestOrientationTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x000215A0L, 0x000217F0L, 0x00021860L, 0x000218E0L, 0x00021900L,
        0x00021930L, 0x00021940L, 0x00021970L,
        0x00022C00L, 0x000233C0L, 0x000235E0L, 0x000243D0L,
        0x00031110L,
        0x0008FAD0L, 0x0008FD90L, 0x000901E0L, 0x00090570L, 0x00091890L,
        0x00093800L, 0x000951D0L, 0x00095B40L, 0x00095C70L, 0x00095FB0L,
        0x00095D40L, 0x00096050L, 0x000960E0L, 0x00096590L, 0x00096600L,
        0x00096A80L,
        0x00096B20L, 0x00096B90L,
        0x000DE760L, 0x000DE7B0L, 0x000DE980L, 0x000DF700L,
        0x0013E810L, 0x0013E830L,
        0x001C0340L, 0x001C12E0L, 0x001C2320L, 0x001C2340L,
        0x001C2530L, 0x001C2870L, 0x001C3560L,
        0x002176D0L, 0x002177A0L, 0x002178E0L,
        0x003CA150L, 0x003CA1E0L, 0x003CA3D0L
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

    private String bytes(long va, int size) throws Exception {
        byte[] data = new byte[size];
        int read = currentProgram.getMemory().getBytes(address(va), data);
        if (read != size) throw new IllegalStateException("short read at " + hex(va));
        StringBuilder result = new StringBuilder();
        for (byte value : data) result.append(String.format("%02x", value & 0xff));
        return result.toString();
    }

    private void writeFunctionInstructions(BufferedWriter output, Function function)
            throws Exception {
        Instruction instruction = currentProgram.getListing().getInstructionAt(
            function.getEntryPoint());
        while (instruction != null && function.getBody().contains(instruction.getAddress())) {
            output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " + instruction +
                " refs=" + String.join(";", referencesTo(instruction.getAddress())) + "\n");
            instruction = instruction.getNext();
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflRestOrientationTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "nfl_rest_orientation_trace.txt")))) {
            trace.write("NFL 2K5 rest-orientation/current-matrix focused trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");
            trace.write("CONSTANT_BYTES\n");
            trace.write("0x004E4180=" + bytes(0x004E4180L, 0x40) + "\n");
            trace.write("0x004E5C60=" + bytes(0x004E5C60L, 0x40) + "\n\n");
            trace.write("FOCUSED_FUNCTION_REFERENCES\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                trace.write(hex(value) + " " + functionName(function) + " refs=" +
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
                new File(directory, "nfl_rest_orientation_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 rest-orientation/current-matrix focused pseudo-C. */\n\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 180 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
            pseudo.write("// PORTME: prove the geometric source/target frames of 0x001C2530 and 0x001C2870.\n");
            pseudo.write("// PORTME: prove model-space versus world-space ownership at every 0x00022C00 caller.\n");
            pseudo.write("// PORTME: prove vector-lane axes, handedness, units, and root-motion composition.\n");
            pseudo.write("// PORTME: do not emit skeletal glTF from an incomplete rest-orientation contract.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_REST_ORIENTATION_TRACE_COMPLETE functions=" + functions.size());
    }
}
