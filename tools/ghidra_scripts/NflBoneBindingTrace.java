// Emit focused NFL 2K5 logical-channel/SCNE-transform binding evidence.
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

public class NflBoneBindingTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00021930L, 0x00023690L, 0x000236B0L, 0x00023710L,
        0x00023730L, 0x000901E0L, 0x00090570L, 0x00091890L,
        0x00095B40L, 0x00095D40L, 0x00095FB0L, 0x00096590L,
        0x00096600L, 0x00096A80L, 0x000DF700L, 0x002176D0L
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

    private String utf16(long va) throws Exception {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < 128; index++) {
            int value = currentProgram.getMemory().getShort(address(va + index * 2L)) & 0xffff;
            if (value == 0) return result.toString();
            result.append((char)value);
        }
        throw new IllegalStateException("unterminated UTF-16 string at " + hex(va));
    }

    private void writePointerStrings(BufferedWriter output, String label, long va, int count)
            throws Exception {
        output.write(label + "_RAW=" + bytes(va, count * 4) + "\n");
        for (int index = 0; index < count; index++) {
            long pointer = Integer.toUnsignedLong(
                currentProgram.getMemory().getInt(address(va + index * 4L)));
            output.write(label + "[" + index + "]=" + hex(pointer) + ":" + utf16(pointer) + "\n");
        }
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
                "usage: NflBoneBindingTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "nfl_bone_binding_trace.txt")))) {
            trace.write("NFL 2K5 logical-channel/SCNE-transform binding trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("PLAYER_MAP_0051CD70=" + bytes(0x0051CD70L, 50) + "\n");
            trace.write("PLAYER_PARENT_0051CDA8=" + bytes(0x0051CDA8L, 100) + "\n");
            trace.write("SHARED_MAP_0051D010=" + bytes(0x0051D010L, 50) + "\n");
            trace.write("SHARED_PARENT_0051D048=" + bytes(0x0051D048L, 100) + "\n\n");
            writePointerStrings(trace, "PLAYER_TRANSFORM_NAMES_004EEAD4", 0x004EEAD4L, 3);
            writePointerStrings(trace, "COACH_TRANSFORM_NAMES_004EFE8C", 0x004EFE8CL, 4);
            writePointerStrings(trace, "REFEREE_TRANSFORM_NAMES_004EFF34", 0x004EFF34L, 4);
            trace.write("PLAYER_SKEL_NAME=" + utf16(0x00E655E0L) + "\n");
            trace.write("PLAYER_SCNE_NAME=" + utf16(0x00E63E60L) + "\n");
            trace.write("COACH_SCNE_NAME=" + utf16(0x00E65BACL) + "\n");
            trace.write("REFEREE_SCNE_NAME=" + utf16(0x00E65DD0L) + "\n");
            trace.write("REFEREE_SHAPE_NAME=" + utf16(0x00E65CBCL) + "\n\n");

            trace.write("SHAPE_TRANSFORM_HELPERS\n");
            writeInstructions(trace, 0x00021930L, 0x00021934L);
            writeInstructions(trace, 0x00023690L, 0x00023734L);
            trace.write("\nPLAYER_SCENE_TO_TRANSFORM_INDEX\n");
            writeInstructions(trace, 0x0009063BL, 0x000906FDL);
            trace.write("\nCOACH_SCENE_TO_TRANSFORM_INDEX\n");
            writeInstructions(trace, 0x00095E94L, 0x00095EFAL);
            trace.write("\nREFEREE_SCENE_TO_TRANSFORM_INDEX\n");
            writeInstructions(trace, 0x0009665BL, 0x000966CFL);
            trace.write("\nSAMPLED_SLOT_CALLBACKS\n");
            writeInstructions(trace, 0x000901E0L, 0x00090247L);
            writeInstructions(trace, 0x00091890L, 0x000918AAL);
            writeInstructions(trace, 0x00095B40L, 0x00095BA9L);
            writeInstructions(trace, 0x00095FB0L, 0x00096007L);
            writeInstructions(trace, 0x00096590L, 0x000965F9L);
            writeInstructions(trace, 0x00096A80L, 0x00096ACCL);
            trace.write("\nSAMPLER_LOGICAL_OUTPUT_STRIDE\n");
            writeInstructions(trace, 0x000DF7B6L, 0x000DF8A5L);
            trace.write("\nPARENT_TABLE_POSE_QUERY\n");
            writeInstructions(trace, 0x002176D0L, 0x00217793L);

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
                new File(directory, "nfl_bone_binding_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 logical-channel/SCNE-transform focused pseudo-C. */\n\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 90 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
            pseudo.write("// PORTME: recover transform record +0x00..+0x5f semantics.\n");
            pseudo.write("// PORTME: prove vertex joint/weight inputs and inverse bind matrices.\n");
            pseudo.write("// PORTME: prove axes, handedness, units, and root-motion application.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_BONE_BINDING_TRACE_COMPLETE functions=" + functions.size());
    }
}
