// Read-only, address-led trace for NFL 2K5's Team Select preview screen.
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

public class NflTeamSelectPreviewOwnerTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";

    private static final long[] FOCUSED = {
        0x00042F50L, 0x000443D0L, 0x000449E0L,
        0x00064BF0L, 0x00068D70L, 0x00068DC0L, 0x00068FD0L, 0x00069D60L,
        0x002C25F0L,
        0x0031E6C0L, 0x0031E750L, 0x0031E7D0L, 0x0031E880L, 0x0031E910L,
        0x0031E960L, 0x0031EA40L, 0x0031EA90L, 0x0031EAB0L,
        0x0031EE50L, 0x0031EED0L, 0x0031EF00L, 0x0031EF10L,
        0x0031EF40L, 0x0031F010L, 0x0031F060L, 0x0031F0A0L,
        0x0031F1D0L, 0x0031F4E0L, 0x0031F760L, 0x0031F7C0L,
        0x00320370L,
    };

    private static final long[][] TRANSIENT_RANGES = {
        {0x002C0A00L, 0x002C0C30L},
        {0x002C1250L, 0x002C13D0L},
        {0x002C1660L, 0x002C1760L},
        {0x002C20F0L, 0x002C2250L},
        {0x002C23D0L, 0x002C2480L},
        {0x002C25F0L, 0x002C2670L},
        {0x0031E960L, 0x0031F900L},
        {0x00320370L, 0x00320500L},
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String hex(Address value) {
        return value == null ? "none" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        return function == null ? "none" : hex(function.getEntryPoint()) + ":" + function.getName();
    }

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            result.append(String.format("%02x", value & 0xff));
        }
        return result.toString();
    }

    private String rawBytes(long first, int count) throws Exception {
        byte[] data = new byte[count];
        int read = currentProgram.getMemory().getBytes(address(first), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(first));
        StringBuilder result = new StringBuilder();
        for (byte value : data) result.append(String.format("%02x", value & 0xff));
        return result.toString();
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

    private void writeRange(BufferedWriter output, long first, long afterLast,
            Set<Function> functions) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast - 1) + "\n");
        long value = first;
        while (value < afterLast) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                // This modifies only the transient listing opened with -readOnly.  It does
                // not create a saved function or modify the executable/project.
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(value) + " db " + rawBytes(value, 1) +
                    " // inline data or decoder-rejected byte\n");
                value++;
                continue;
            }
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            if (owner != null) functions.add(owner);
            List<String> outgoing = new ArrayList<>();
            for (Reference reference : instruction.getReferencesFrom()) {
                outgoing.add(reference.getReferenceType() + ":" + hex(reference.getToAddress()));
            }
            output.write(hex(instruction.getAddress()) + " " + bytes(instruction) + " " +
                instruction + " owner=" + functionName(owner) + " outgoing=" +
                String.join(";", outgoing) + " incoming=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
            value = instruction.getMaxAddress().getUnsignedOffset() + 1;
        }
        output.write("\n");
    }

    private void writeFunctionInstructions(BufferedWriter output, Function function)
            throws Exception {
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            List<String> outgoing = new ArrayList<>();
            for (Reference reference : instruction.getReferencesFrom()) {
                outgoing.add(reference.getReferenceType() + ":" + hex(reference.getToAddress()));
            }
            output.write(hex(instruction.getAddress()) + " " + bytes(instruction) + " " +
                instruction + " outgoing=" + String.join(";", outgoing) + "\n");
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflTeamSelectPreviewOwnerTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "nfl_team_select_preview_owner_trace.txt")))) {
            output.write("NFL 2K5 Team Select preview-owner trace\n");
            output.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            output.write("Saved project opened read-only; transient disassembly is discarded.\n\n");

            output.write("TEAM_SELECT_STATE\n");
            output.write("descriptor 0x0052728C bytes=" + rawBytes(0x0052728CL, 0x20) + "\n");
            output.write("title=" + utf16(u32(0x0052728CL), 64) + "\n");
            output.write("event_table=" + hex(u32(0x00527290L)) +
                " default_callback=" + hex(u32(0x00527294L)) + "\n");
            output.write("event_table_bytes=" + rawBytes(0x00527228L, 0x58) + "\n\n");

            output.write("ACTION_DESCRIPTORS\n");
            for (long item = 0x00526F58L; item <= 0x005271E0L; item += 0x48L) {
                output.write(hex(item) + " selector=" + u32(item) +
                    " callback=" + hex(u32(item + 4)) + " bytes=" +
                    rawBytes(item, 0x48) + "\n");
            }
            output.write("\n");

            output.write("SCENE_AND_MATERIAL_STRINGS\n");
            long[] strings = {
                0x00EA2D14L, 0x00EA2D3CL,
                0x00EA2BF8L, 0x00EA2B38L,
                0x00EA2BACL, 0x00EA2AE8L,
                0x00EA2B18L, 0x00EA2BD8L,
                0x00EA2B60L, 0x00EA2C20L,
                0x00EA2C78L, 0x00EA2C94L, 0x00EA2CB0L,
                0x00EA2CDCL, 0x00EA2CE0L, 0x00EA2CFCL,
                0x00E9AA08L, 0x00E9AA14L, 0x00E9AA18L, 0x00E9AA24L,
            };
            for (long value : strings) {
                output.write(hex(value) + " text=" + utf16(value, 96) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }
            output.write("\nMATERIAL_POINTER_TABLE\n");
            for (long item = 0x00AE2C60L; item <= 0x00AE2CA4L; item += 4) {
                long pointer = u32(item);
                output.write(hex(item) + " pointer=" + hex(pointer) +
                    " text=" + utf16(pointer, 64) + "\n");
            }
            output.write("\nSCENE_GLOBAL_REFERENCES\n");
            long[] globals = {
                0x00A83A1CL,
                0x00AE2B34L, 0x00AE2B38L, 0x00AE2B3CL, 0x00AE2B40L,
                0x00AE2B44L, 0x00AE2B48L, 0x00AE2C4CL, 0x00AE2D00L,
            };
            for (long value : globals) {
                output.write(hex(value) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }

            output.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                if (function == null) {
                    output.write(hex(value) + " missing_saved_boundary\n");
                    continue;
                }
                functions.add(function);
                output.write(functionName(function) + " body=" +
                    hex(function.getBody().getMinAddress()) + ".." +
                    hex(function.getBody().getMaxAddress()) + " refs=" +
                    String.join(";", referencesTo(function.getEntryPoint())) + "\n");
            }

            output.write("\nTRANSIENT_INSTRUCTIONS\n");
            for (long[] range : TRANSIENT_RANGES) {
                writeRange(output, range[0], range[1], functions);
            }

            output.write("SAVED_FUNCTION_INSTRUCTIONS\n");
            List<Function> ordered = new ArrayList<>(functions);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : ordered) {
                output.write("\nFUNCTION " + functionName(function) + "\n");
                writeFunctionInstructions(output, function);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_team_select_preview_owner_pseudo_c.c")))) {
            output.write("/* NFL 2K5 Team Select preview-owner saved-boundary pseudo-C. */\n\n");
            List<Function> ordered = new ArrayList<>(functions);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : ordered) {
                output.write("/* " + functionName(function) + " body=" +
                    hex(function.getBody().getMinAddress()) + ".." +
                    hex(function.getBody().getMaxAddress()) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 120 seconds" :
                        result.getErrorMessage();
                    output.write("// PORTME: could not decompile " + functionName(function) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                output.write("\n");
            }
            output.write("// PORTME: action callbacks lacking saved boundaries remain exact transient disassembly only.\n");
            output.write("// PORTME: capture FUN_000449e0 returns to distinguish duplicate double_team_select SCNE records in a live run.\n");
            output.write("// PORTME: capture DAT_00a83a1c and the FUN_000449e0 context argument to prove the live global-versus-LOGOS TXTR lookup branch.\n");
            output.write("// PORTME: capture material+0x30 after FUN_0031ea90 to prove live TXTR pointers independently of screenshot matching.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_TEAM_SELECT_PREVIEW_OWNER_TRACE_COMPLETE functions=" + functions.size());
    }
}
