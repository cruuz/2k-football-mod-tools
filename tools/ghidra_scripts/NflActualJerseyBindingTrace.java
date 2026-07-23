// Read-only, address-led trace for NFL 2K5 player-uniform texture binding.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflActualJerseyBindingTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";

    private static final long[] FOCUSED = {
        0x00038650L, 0x00043F50L, 0x000449E0L, 0x00045300L,
        0x000615A0L, 0x00062BE0L,
        0x0008E3F0L, 0x0008E430L, 0x0008E470L, 0x0008E4B0L,
        0x0008E580L, 0x0008E5C0L, 0x0008E620L,
        0x0008E830L, 0x0008E850L, 0x0008E870L, 0x0008E8D0L,
        0x0008E910L,
        0x0008E9E0L, 0x0008EBB0L, 0x0008ECF0L, 0x0008EDB0L,
        0x0008EE40L, 0x0008EEB0L, 0x0008EF20L, 0x0008EFA0L,
        0x00090570L,
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String hex(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        return function == null ? "none" : hex(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(hex(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private long u32(long value) throws Exception {
        Address start = address(value);
        Memory memory = currentProgram.getMemory();
        return (memory.getByte(start) & 0xffL) |
            ((memory.getByte(start.add(1)) & 0xffL) << 8) |
            ((memory.getByte(start.add(2)) & 0xffL) << 16) |
            ((memory.getByte(start.add(3)) & 0xffL) << 24);
    }

    private String utf16(long value, int maximum) throws Exception {
        if (value == 0 || !currentProgram.getMemory().contains(address(value))) return "";
        Memory memory = currentProgram.getMemory();
        StringBuilder output = new StringBuilder();
        for (int index = 0; index < maximum; index++) {
            Address cursor = address(value + index * 2L);
            int code = (memory.getByte(cursor) & 0xff) |
                ((memory.getByte(cursor.add(1)) & 0xff) << 8);
            if (code == 0) break;
            if (code >= 0x20 && code < 0x7f) output.append((char)code);
            else output.append(String.format("\\u%04X", code));
        }
        return output.toString();
    }

    private String bytes(long value, int count) throws Exception {
        byte[] data = new byte[count];
        int read = currentProgram.getMemory().getBytes(address(value), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(value));
        StringBuilder output = new StringBuilder();
        for (byte item : data) output.append(String.format("%02x", item & 0xff));
        return output.toString();
    }

    private void writeInstructions(BufferedWriter output, Function function) throws Exception {
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress()) + " " + instruction + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
    }

    private void writeRange(BufferedWriter output, long first, long afterLast) throws Exception {
        Address cursor = address(first);
        Address limit = address(afterLast);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                output.write(hex(cursor) + " DB " + bytes(cursor.getUnsignedOffset(), 1) + "\n");
                cursor = cursor.add(1);
            }
            else {
                output.write(hex(cursor) + " " + instruction + " refs=" +
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
                "usage: NflActualJerseyBindingTrace.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable MD5 " +
                currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> functions = new LinkedHashSet<>();
        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_actual_jersey_binding_trace.txt")))) {
            output.write("NFL 2K5 actual player-jersey binding trace\n");
            output.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            output.write("Read-only saved-project analysis; all addresses are loaded XBE VAs.\n\n");

            output.write("FOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                if (function == null) {
                    throw new IllegalStateException("missing focused function at " + hex(value));
                }
                functions.add(function);
                output.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }

            output.write("\nCONTEXT_POINTERS\n");
            for (long slot = 0x004EEACCL; slot <= 0x004EEAD0L; slot += 4) {
                long pointer = u32(slot);
                output.write(hex(slot) + " pointer=" + hex(pointer) + " text=" +
                    utf16(pointer, 32) + "\n");
            }

            output.write("\nPLAYER_TEXTURE_BINDING_TABLE\n");
            int index = 0;
            for (long slot = 0x004EEAF8L; slot <= 0x004EEDF0L; slot += 8, index++) {
                long pointer = u32(slot);
                long localFirst = u32(slot + 4);
                output.write(String.format(
                    "index=%02d slot=%s pointer=%s local_first=0x%08X text=%s\n",
                    index, hex(slot), hex(pointer), localFirst, utf16(pointer, 64)));
            }

            output.write("\nMATERIAL_NAMES\n");
            for (long slot = 0x004EEE68L; slot <= 0x004EEF5CL; slot += 4) {
                long pointer = u32(slot);
                output.write(hex(slot) + " pointer=" + hex(pointer) + " text=" +
                    utf16(pointer, 80) + "\n");
            }

            output.write("\nTEXTURE_ROUTING_TABLES\n");
            for (long slot = 0x004EF388L; slot <= 0x004EF3C4L; slot += 4) {
                output.write(hex(slot) + " value=" + hex(u32(slot)) + "\n");
            }
            output.write(hex(0x004EF874L) + " value=" + hex(u32(0x004EF874L)) + "\n");

            output.write("\nDYNAMIC_DIGIT_TEXTURE_TABLE\n");
            for (long slot = 0x00A86C00L; slot <= 0x00A86D68L; slot += 4) {
                long value = u32(slot);
                output.write(hex(slot) + " value=" + hex(value));
                if (value != 0 && currentProgram.getMemory().contains(address(value))) {
                    output.write(" text=" + utf16(value, 32));
                }
                output.write("\n");
            }

            output.write("\nBODY_UNIFORM_ROUTING_TABLES\n");
            for (long slot = 0x004EF3C8L; slot <= 0x004EF450L; slot += 4) {
                long value = u32(slot);
                output.write(hex(slot) + " value=" + hex(value));
                if (value < 62) {
                    long pointer = u32(0x004EEE68L + value * 4L);
                    output.write(" possible_material_index=" + value +
                        " possible_material=" + utf16(pointer, 80));
                }
                output.write("\n");
            }
            output.write("\nNUMBER_MATERIAL_ROUTING_TABLES\n");
            for (long slot = 0x004EF7F8L; slot <= 0x004EF874L; slot += 4) {
                output.write(hex(slot) + " value=" + hex(u32(slot)) + "\n");
            }

            output.write("\nFILENAME_AND_BINDING_STRINGS\n");
            long[] strings = {
                0x00E61060L, 0x00E6162CL, 0x00E61638L,
                0x00E63F50L, 0x00E63F78L, 0x00E63FA4L, 0x00E63FB8L,
                0x00E63FCCL, 0x00E63FDCL,
                0x00E64CB4L, 0x00E64CCCL, 0x00E64CE4L,
            };
            for (long value : strings) {
                output.write(hex(value) + " text=" + utf16(value, 80) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }

            output.write("\nEXACT_SELECTION_RANGES\n");
            output.write("RANGE 0x00061670..0x00061703 (%s%c%d.iff producer)\n");
            writeRange(output, 0x00061670L, 0x00061703L);
            output.write("RANGE 0x00063261..0x0006329D (HOME/AWAY context load calls)\n");
            writeRange(output, 0x00063261L, 0x0006329DL);
            output.write("RANGE 0x00045280..0x00045300 (TSET loader callback; undefined boundary retained)\n");
            writeRange(output, 0x00045280L, 0x00045300L);

            output.write("\nFOCUSED_INSTRUCTIONS\n");
            for (Function function : functions) {
                output.write("\nFUNCTION " + functionName(function) + "\n");
                writeInstructions(output, function);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_actual_jersey_binding_pseudo_c.c")))) {
            output.write("/* NFL 2K5 actual player-jersey binding focused pseudo-C. */\n\n");
            List<Function> ordered = new ArrayList<>(functions);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : ordered) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 180 seconds" :
                        result.getErrorMessage();
                    output.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                output.write("\n");
            }
            output.write("// PORTME: callback 0x00045280 lacks a saved Ghidra function boundary; exact bytes/instructions are retained in the trace.\n");
            output.write("// PORTME: prove runtime values selecting clean/mud and HOME/AWAY array quadrants before interpreting a negative emulator capture.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_ACTUAL_JERSEY_BINDING_TRACE_COMPLETE functions=" + functions.size());
    }
}
