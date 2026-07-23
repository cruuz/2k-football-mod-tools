// Emit focused NFL 2K5 compressed-position relocation/render evidence.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class NflNormshort3Trace extends GhidraScript {
    private static final long RELOCATOR = 0x00022F90L;
    private static final long RENDER = 0x000243D0L;
    private static final long SHADER_OBJECT_FIRST = 0x00A6C540L;
    private static final int SHADER_OBJECT_COUNT = 13;
    private static final int SHADER_OBJECT_STRIDE = 0x20;

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String bytes(long va, int size) throws Exception {
        byte[] data = new byte[size];
        currentProgram.getMemory().getBytes(address(va), data);
        StringBuilder result = new StringBuilder();
        for (byte value : data) result.append(String.format("%02x", value & 0xff));
        return result.toString();
    }

    private long unsignedInt(long va) throws Exception {
        return currentProgram.getMemory().getInt(address(va)) & 0xffffffffL;
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
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
                    " owner=" + functionName(owner) + "\n");
                cursor = instruction.getMaxAddress().add(1);
            }
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: NflNormshort3Trace.java OUTPUT_DIRECTORY");
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

        try (BufferedWriter trace = new BufferedWriter(new FileWriter(
                new File(directory, "normshort3_trace.txt")))) {
            trace.write("NFL 2K5 NORMSHORT3 position trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("RELOCATOR_WINDOW_00022F90=" + bytes(0x00022F90L, 0x40) + "\n");
            trace.write("RENDER_UPLOAD_000245FD=" + bytes(0x000245FDL, 0x3A) + "\n");
            trace.write("SHADER_OBJECT_TABLE_00A6C540=" +
                bytes(SHADER_OBJECT_FIRST, SHADER_OBJECT_COUNT * SHADER_OBJECT_STRIDE) + "\n\n");

            trace.write("RELOCATOR_INSTRUCTIONS\n");
            writeInstructions(trace, 0x00022F90L, 0x00022FD0L);
            trace.write("\nRENDER_UPLOAD_INSTRUCTIONS\n");
            writeInstructions(trace, 0x000245FDL, 0x0002463DL);

            trace.write("\nSTATIC_SHADER_OBJECTS\n");
            for (int index = 0; index < SHADER_OBJECT_COUNT; ++index) {
                long objectVa = SHADER_OBJECT_FIRST + index * SHADER_OBJECT_STRIDE;
                long declaration = unsignedInt(objectVa + 8);
                long version = unsignedInt(objectVa + 12);
                long instructionCount = unsignedInt(objectVa + 20);
                long programVa = unsignedInt(objectVa + 28);
                trace.write(String.format(
                    "object=%02d va=%s declaration=0x%08X version=0x%04X " +
                    "instruction_count=%d program=%s instruction_1=%08X %08X %08X %08X\n",
                    index, hex(objectVa), declaration, version, instructionCount,
                    hex(programVa), unsignedInt(programVa + 16), unsignedInt(programVa + 20),
                    unsignedInt(programVa + 24), unsignedInt(programVa + 28)));
            }
            trace.write("\nDECODED_COMMON_INSTRUCTION\n");
            trace.write("MAD r4.xyz, v0.xyzz, c[-88].wwww, c[-88].xyzz\n");
            trace.write("r4.xyz = v0.xyz * c[-88].w + c[-88].xyz\n");
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory, "normshort3_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 NORMSHORT3 focused pseudo-C. */\n\n");
            for (long value : new long[] {RELOCATOR, RENDER}) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                if (function == null) {
                    throw new IllegalStateException("missing focused function at " + hex(value));
                }
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 120 seconds" :
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
        println("NFL_NORMSHORT3_TRACE_COMPLETE shaders=" + SHADER_OBJECT_COUNT);
    }
}
