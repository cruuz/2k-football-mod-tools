// Read-only, address-led trace for NFL 2K5 live number/nameplate composition.
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

public class NflLiveNumbersNameplateTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";
    private static final long[] FOCUSED = {
        0x000449E0L, 0x0008E3F0L, 0x0008E4B0L, 0x0008E580L,
        0x0008E5C0L, 0x0008E620L, 0x0008E8D0L, 0x0008E910L,
        0x0008EFA0L, 0x0008F800L, 0x00090570L,
        0x001C20B0L, 0x001C20F0L, 0x001C2140L, 0x003D0820L,
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) { return String.format("0x%08X", value); }
    private String hex(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }
    private String functionName(Function function) {
        return function == null ? "none" : hex(function.getEntryPoint()) + ":" + function.getName();
    }

    private long u32(long value) throws Exception {
        Memory memory = currentProgram.getMemory();
        Address start = address(value);
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

    private void writeInstructions(BufferedWriter output, Function function) throws Exception {
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress()) + " " + instruction + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflLiveNumbersNameplateTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "nfl_live_numbers_nameplate_trace.txt")))) {
            output.write("NFL 2K5 live numbers/nameplate static trace\n");
            output.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            output.write("Read-only saved-project analysis; addresses are loaded XBE VAs.\n\n");

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

            output.write("\nHOME_AWAY_CONTEXTS\n");
            for (long slot = 0x004EEACCL; slot <= 0x004EEAD0L; slot += 4) {
                long pointer = u32(slot);
                output.write(hex(slot) + " pointer=" + hex(pointer) + " text=" +
                    utf16(pointer, 32) + "\n");
            }

            output.write("\nPLAYER_TEXTURE_BINDING_TABLE\n");
            int index = 0;
            for (long slot = 0x004EEAF8L; slot <= 0x004EEDF0L; slot += 8, index++) {
                long pointer = u32(slot);
                output.write(String.format(
                    "index=%02d slot=%s pointer=%s local_first=0x%08X text=%s\n",
                    index, hex(slot), hex(pointer), u32(slot + 4), utf16(pointer, 64)));
            }

            output.write("\nDYNAMIC_DIGIT_CACHE_TABLE\n");
            for (long slot = 0x00A86C00L; slot <= 0x00A86D70L; slot += 4) {
                long value = u32(slot);
                output.write(hex(slot) + " value=" + hex(value));
                if (value != 0 && currentProgram.getMemory().contains(address(value))) {
                    output.write(" text=" + utf16(value, 32));
                }
                output.write("\n");
            }

            output.write("\nNUMBER_AND_NAMEPLATE_MATERIAL_ROUTES\n");
            for (long slot = 0x004EF7F8L; slot <= 0x004EF874L; slot += 4) {
                output.write(hex(slot) + " value=" + hex(u32(slot)) + "\n");
            }

            output.write("\nRESOURCE_STRINGS\n");
            long[] strings = {
                0x00E63F50L, 0x00E63F78L, 0x00E63FA4L,
                0x00E63FB8L, 0x00E63FCCL, 0x00E63FDCL,
                0x00E655C4L, 0x00E655D4L,
            };
            for (long value : strings) {
                output.write(hex(value) + " text=" + utf16(value, 80) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }

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
                new File(directory, "nfl_live_numbers_nameplate_pseudo_c.c")))) {
            output.write("/* NFL 2K5 live numbers/nameplate focused pseudo-C. */\n\n");
            List<Function> ordered = new ArrayList<>(functions);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : ordered) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    output.write("/* PORTME: could not decompile " + functionName(function) +
                        ": " + result.getErrorMessage() + " */\n");
                }
                output.write("\n\n");
            }
        }
        finally {
            decompiler.dispose();
        }
    }
}
