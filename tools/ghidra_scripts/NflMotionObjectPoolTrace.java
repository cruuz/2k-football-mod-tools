// Emit focused NFL 2K5 motion-controller object-pool evidence.
// @category Xbox.NFL2K5

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

public class NflMotionObjectPoolTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x0011A540L, 0x00074D40L, 0x00075B30L, 0x000DD6A0L,
        0x000DDAD0L, 0x001D2B00L, 0x00217E10L, 0x00217EB0L,
        0x00217F20L
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

    private String bytes(long va, int size) throws Exception {
        byte[] data = new byte[size];
        currentProgram.getMemory().getBytes(address(va), data);
        StringBuilder result = new StringBuilder();
        for (byte value : data) result.append(String.format("%02x", value & 0xff));
        return result.toString();
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
            throw new IllegalArgumentException(
                "usage: NflMotionObjectPoolTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "motion_object_pool_trace.txt")))) {
            trace.write("NFL 2K5 motion object-pool trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("ALLOCATION_TABLE_004F9E98=" + bytes(0x004F9E98L, 100) + "\n");
            trace.write("SEVEN_ACTOR_RECORDS_0050DF00=" + bytes(0x0050DF00L, 196) + "\n");
            trace.write("TEAM_AFFILIATED_RECORDS_0050DFC4=" +
                bytes(0x0050DFC4L, 56) + "\n\n");

            trace.write("ALLOCATION_CALL_SITE\n");
            writeInstructions(trace, 0x0011A540L, 0x0011A5B0L);
            trace.write("\nPOOL_ALLOCATORS\n");
            writeInstructions(trace, 0x00074D40L, 0x00074DB8L);
            writeInstructions(trace, 0x00075B30L, 0x00075BC8L);
            writeInstructions(trace, 0x000DD6A0L, 0x000DD715L);
            writeInstructions(trace, 0x000DDAD0L, 0x000DDB30L);
            trace.write("\nTEAM_BINDING\n");
            writeInstructions(trace, 0x001D2B00L, 0x001D2B40L);
            trace.write("\nMAP_INSTALLERS\n");
            writeInstructions(trace, 0x00217E10L, 0x00217F8FL);

            trace.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                trace.write(hex(value) + " " + functionName(function) + "\n");
                if (function == null) {
                    throw new IllegalStateException(
                        "missing focused function boundary at " + hex(value));
                }
                functions.add(function);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory, "motion_object_pool_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 motion object-pool focused pseudo-C. */\n\n");
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
        println("NFL_MOTION_OBJECT_POOL_TRACE_COMPLETE functions=" + functions.size());
    }
}
