// Emit focused NFL 2K5 SCNE transform, palette, and vertex-shader evidence.
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

public class NflTransformSemanticsTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00021860L, 0x00021E40L, 0x00021EB0L,
        0x00022950L, 0x00022A70L, 0x00022C00L, 0x00022F90L,
        0x00023690L, 0x000236B0L, 0x00023710L, 0x00023730L,
        0x00024160L, 0x000243D0L,
        0x000DE810L, 0x000DE910L,
        0x000901E0L, 0x00090570L, 0x00091890L,
        0x00095B40L, 0x00095D40L, 0x00095FB0L,
        0x00096590L, 0x00096600L, 0x00096A80L,
        0x001C2530L, 0x001C2870L, 0x002176D0L, 0x003CA150L
    };

    private static final long SHADER_OBJECT_FIRST = 0x00A6C540L;
    private static final int SHADER_OBJECT_COUNT = 13;
    private static final int SHADER_OBJECT_STRIDE = 0x20;

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

    private long unsignedInt(long va) throws Exception {
        return Integer.toUnsignedLong(currentProgram.getMemory().getInt(address(va)));
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

    private void writeShaderObjects(BufferedWriter output) throws Exception {
        output.write("SHADER_OBJECT_TABLE=" +
            bytes(SHADER_OBJECT_FIRST, SHADER_OBJECT_COUNT * SHADER_OBJECT_STRIDE) + "\n");
        for (int index = 0; index < SHADER_OBJECT_COUNT; ++index) {
            long objectVa = SHADER_OBJECT_FIRST + index * SHADER_OBJECT_STRIDE;
            long instructionCount = unsignedInt(objectVa + 0x14);
            long programVa = unsignedInt(objectVa + 0x1C);
            output.write(String.format(
                "object=%02d va=%s declaration=0x%08X version=0x%04X " +
                "instruction_count=%d program=%s bytes=%s\n",
                index, hex(objectVa), unsignedInt(objectVa + 8),
                unsignedInt(objectVa + 12), instructionCount, hex(programVa),
                bytes(programVa, Math.toIntExact(instructionCount * 16L))));
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflTransformSemanticsTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "nfl_transform_semantics_trace.txt")))) {
            trace.write("NFL 2K5 SCNE transform/palette/shader focused trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");
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
            trace.write("\nVERTEX_SHADER_OBJECTS\n");
            writeShaderObjects(trace);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_transform_semantics_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 SCNE transform/palette/shader focused pseudo-C. */\n\n");
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
            pseudo.write("// PORTME: prove any transform field not established by this trace.\n");
            pseudo.write("// PORTME: prove axes, handedness, units, and root-motion composition.\n");
            pseudo.write("// PORTME: do not emit skeletal glTF until bind and palette contracts are complete.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_TRANSFORM_SEMANTICS_TRACE_COMPLETE functions=" + functions.size());
    }
}
