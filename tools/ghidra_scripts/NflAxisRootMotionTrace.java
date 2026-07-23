// Emit focused NFL 2K5 coordinate-axis, unit, and root-motion evidence.
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

public class NflAxisRootMotionTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        // Immediate-mode position writer and the field/end-zone coordinate consumer.
        0x0002CA70L, 0x0002CB50L, 0x0009B080L, 0x0009B880L,
        0x0009B950L, 0x0009BE70L, 0x0009C160L,

        // Raw trajectory sampling, per-axis accessors, and interval delta builder.
        0x000DEE30L, 0x000DF220L, 0x000DF2F0L, 0x000DF3D0L,

        // Skeleton/root composition and the exact fixed-turn sine/cosine helper.
        0x002171C0L, 0x002176D0L, 0x002177A0L, 0x002178E0L,
        0x00218150L,

        // Local motion-to-object and object-to-external-parent/world composition.
        0x00304700L, 0x00304980L, 0x00304B50L, 0x00304BF0L,

        // Player current-matrix path and shared matrix/quaternion convention.
        0x000233C0L, 0x0005C530L, 0x00093800L, 0x0035B520L,
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
                "usage: NflAxisRootMotionTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "nfl_axis_root_motion_trace.txt")))) {
            trace.write("NFL 2K5 coordinate-axis/unit/root-motion focused trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");

            trace.write("CONSTANT_BYTES\n");
            trace.write("trajectory_scale_0x004F24E4=" + bytes(0x004F24E4L, 4) + "\n");
            trace.write("fixed_sine_table_0x004E53E8=" + bytes(0x004E53E8L, 0x800) + "\n");
            trace.write("field_interval_table_0x004F01C8=" + bytes(0x004F01C8L, 0x110) + "\n");
            trace.write("field_constants_0x004F02D8=" + bytes(0x004F02D8L, 0x38) + "\n\n");

            trace.write("KEY_REFERENCES\n");
            long[] targets = {
                0x0002CB50L, 0x0009BE70L, 0x000DEE30L, 0x000DF220L,
                0x000DF2F0L, 0x000DF3D0L, 0x002171C0L, 0x00218150L,
                0x00304B50L, 0x00304BF0L, 0x00093800L, 0x004F24E4L,
                0x004E53E8L, 0x004F01C8L,
                // Data-side camera setting labels; refs are retained even if
                // they do not directly prove a spatial convention.
                0x00B2B65CL, 0x00B2B67CL, 0x00B2B698L, 0x00B2FCCCL
            };
            for (long target : targets) {
                trace.write(hex(target) + " refs=" +
                    String.join(";", referencesTo(address(target))) + "\n");
            }

            trace.write("\nFOCUSED_FUNCTION_REFERENCES\n");
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
                new File(directory, "nfl_axis_root_motion_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 coordinate-axis/unit/root-motion focused pseudo-C. */\n\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 240, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 240 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
            pseudo.write("// PORTME at 0x000DF3D0: preserve its asymmetric interval contract: X/Z/turn are differences, Y is the absolute end sample.\n");
            pseudo.write("// PORTME at 0x00304BF0: classify every caller's external parent as model, attachment, camera, or world space before flattening nodes.\n");
            pseudo.write("// PORTME at 0x00093800: retain caller-supplied external-root ownership; it is not universally world space.\n");
            pseudo.write("// PORTME: prove scene-node ownership and loop-boundary accumulation before emitting complete glTF root tracks.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_AXIS_ROOT_MOTION_TRACE_COMPLETE functions=" + functions.size());
    }
}
