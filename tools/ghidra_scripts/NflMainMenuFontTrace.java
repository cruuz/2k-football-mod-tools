// Read-only focused trace for NFL 2K5 main-menu FONT selection and glyph draw.
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

public class NflMainMenuFontTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x0002CA00L,
        0x0002CA70L,
        0x0002CB90L,
        0x0002CBE0L,
        0x0002D2A0L,
        0x00046200L,
        0x00046310L,
        0x00046420L,
        0x000469B0L,
        0x00046DF0L,
        0x00047420L,
        0x00049390L,
        0x000493D0L,
        0x000493E0L,
        0x000EF570L,
        0x000EF850L,
        0x000F0140L,
        0x000F1D50L,
        0x0014FDA0L
    };

    private static final long[][] RAW_WINDOWS = {
        { 0x000F0140L, 0x000F1050L },
        { 0x000F1D50L, 0x000F1F1DL },
        { 0x0014FDC0L, 0x0014FF40L }
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

    private void writeRange(BufferedWriter output, long first, long last)
            throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(last) + "\n");
        Address cursor = address(first);
        Address limit = address(last);
        while (cursor.compareTo(limit) <= 0) {
            Instruction instruction = currentProgram.getListing()
                .getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            cursor = instruction == null ? cursor.add(1) :
                instruction.getMaxAddress().add(1);
        }
        InstructionIterator iterator = currentProgram.getListing()
            .getInstructions(address(first), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            long value = instruction.getAddress().getUnsignedOffset();
            if (Long.compareUnsigned(value, last) > 0) break;
            output.write(hex(value) + " " + instruction + " owner=" +
                functionName(currentProgram.getFunctionManager()
                    .getFunctionContaining(instruction.getAddress())) + "\n");
        }
        output.write("\n");
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

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflMainMenuFontTrace.java OUTPUT_DIRECTORY");
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
            "nfl_main_menu_font_trace.txt");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(traceFile))) {
            output.write("NFL 2K5 main-menu FONT/glyph trace\n");
            output.write("Program MD5: " +
                currentProgram.getExecutableMD5() + "\n\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                output.write(hex(value) + " " + functionName(function) + "\n");
                if (function != null) functions.add(function);
            }
            output.write("\nSTATIC_TABLES\n");
            writeBytes(output, 0x000F1054L, 15 * 4);
            writeBytes(output, 0x00A91928L, 10 * 4);
            output.write("\nFUNCTIONS\n");
            for (Function function : functions) {
                writeFunction(output, function);
            }
            output.write("RAW_WINDOWS\n");
            for (long[] window : RAW_WINDOWS) {
                writeRange(output, window[0], window[1]);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory,
            "nfl_main_menu_font_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(pseudoFile))) {
            output.write("/* NFL 2K5 main-menu FONT/glyph pseudo-C */\n\n");
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
        println("NFL_MAIN_MENU_FONT_TRACE_COMPLETE functions=" +
            functions.size());
    }
}
