// Read-only trace for NFL 2K5 main-menu row and text-coordinate construction.
// @category VisualConcepts.NFL

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;

public class NflMainMenuRowLayoutTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x0006E2D0L,
        0x0014FB70L,
        0x0014FDA0L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace()
            .getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" +
            function.getName();
    }

    private void writeBytes(BufferedWriter output, long first, int length)
            throws Exception {
        Memory memory = currentProgram.getMemory();
        byte[] bytes = new byte[length];
        int read = memory.getBytes(address(first), bytes);
        if (read != length) {
            throw new IllegalStateException("short read at " + hex(first));
        }
        StringBuilder builder = new StringBuilder();
        for (byte value : bytes) {
            builder.append(String.format("%02x", value & 0xff));
        }
        output.write(hex(first) + " length=" + length + " bytes=" +
            builder + "\n");
    }

    private void writeFunction(BufferedWriter output, Function function)
            throws Exception {
        output.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody() + "\n");
        InstructionIterator iterator = currentProgram.getListing()
            .getInstructions(function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress().getUnsignedOffset()) +
                " " + instruction + "\n");
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflMainMenuRowLayoutTrace.java OUTPUT_DIRECTORY");
        }
        if (!"444064a9ec984dd29d2c05a43f5c96e8".equalsIgnoreCase(
                currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable");
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> functions = new LinkedHashSet<>();
        File traceFile = new File(directory,
            "nfl_main_menu_row_layout_trace.txt");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(traceFile))) {
            output.write("NFL 2K5 main-menu row-layout trace\n");
            output.write("Program MD5: " +
                currentProgram.getExecutableMD5() + "\n\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                output.write(hex(value) + " " + functionName(function) + "\n");
                if (function != null) functions.add(function);
            }
            output.write("\nSTATIC_VALUES\n");
            writeBytes(output, 0x00509A30L, 3 * 16);
            writeBytes(output, 0x004E6C50L, 4);
            writeBytes(output, 0x004E6C6CL, 4);
            writeBytes(output, 0x004E6D40L, 4);
            output.write("\nFUNCTIONS\n");
            for (Function function : functions) {
                writeFunction(output, function);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory,
            "nfl_main_menu_row_layout_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(pseudoFile))) {
            output.write("/* NFL 2K5 main-menu row-layout pseudo-C */\n\n");
            for (Function function : functions) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(
                    function, 90, monitor);
                if (result.decompileCompleted() &&
                        result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    output.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint().getUnsignedOffset()) + "\n");
                }
                output.write("\n\n");
            }
        }
        decompiler.dispose();
        println("NFL_MAIN_MENU_ROW_LAYOUT_TRACE_COMPLETE functions=" +
            functions.size());
    }
}
