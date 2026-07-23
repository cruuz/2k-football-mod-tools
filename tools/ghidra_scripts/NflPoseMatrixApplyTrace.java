// Emit focused NFL 2K5 sampled-pose-to-matrix evidence.
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

public class NflPoseMatrixApplyTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00021860L, 0x00021930L, 0x00021960L, 0x00021970L,
        0x00022C00L, 0x000233C0L, 0x000243D0L, 0x0002EB70L,
        0x00031110L,
        0x0008E350L,
        0x000901E0L, 0x00091890L, 0x000918D0L,
        0x00092140L, 0x00093800L, 0x00093850L,
        0x00095B40L, 0x00095FB0L, 0x00096050L,
        0x00096590L, 0x00096A80L, 0x00096B20L,
        0x000DEE30L, 0x000DF2F0L, 0x000DF3D0L, 0x000DF700L,
        0x0012E0B0L, 0x0012E810L, 0x0012E930L, 0x0012F670L,
        0x00130150L,
        0x002176D0L, 0x002177A0L, 0x002178E0L,
        0x0028AAF0L, 0x0028B140L,
        0x00343220L, 0x0035B520L,
        0x003CA150L, 0x003CA270L, 0x003CA3D0L
    };

    // Ghidra's recovered 0x0012F670 body omits switch arms at 0x0012F7C5..
    // 0x0012F9D8.  Dump the full contiguous bytes/instructions, not only its
    // recovered Function body, so this evidence does not silently lose them.
    private static final long[][] RAW_RANGES = {
        {0x0012F670L, 0x0012FA1BL},
        {0x00130150L, 0x00130E99L},
        {0x0028B140L, 0x0028B24DL},
        {0x00343220L, 0x003432FDL},
        {0x0035B520L, 0x0035B650L}
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

    private String bytes(long start, int size) throws Exception {
        byte[] data = new byte[size];
        int read = currentProgram.getMemory().getBytes(address(start), data);
        if (read != size) throw new IllegalStateException("short read at " + hex(start));
        StringBuilder result = new StringBuilder();
        for (byte value : data) result.append(String.format("%02x", value & 0xff));
        return result.toString();
    }

    private void writeInstruction(BufferedWriter output, Instruction instruction)
            throws Exception {
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
            instruction.getAddress());
        output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " + instruction +
            " owner=" + functionName(owner) + " refs=" +
            String.join(";", referencesTo(instruction.getAddress())) + "\n");
    }

    private void writeFunctionInstructions(BufferedWriter output, Function function)
            throws Exception {
        Instruction instruction = currentProgram.getListing().getInstructionAt(
            function.getEntryPoint());
        while (instruction != null && function.getBody().contains(instruction.getAddress())) {
            writeInstruction(output, instruction);
            instruction = instruction.getNext();
        }
    }

    private void writeRawRange(BufferedWriter output, long start, long end) throws Exception {
        output.write("RANGE " + hex(start) + ".." + hex(end) + " bytes=" +
            bytes(start, (int)(end - start + 1)) + "\n");
        Instruction instruction = currentProgram.getListing().getInstructionAt(address(start));
        if (instruction == null) instruction = currentProgram.getListing().getInstructionAfter(
            address(start));
        while (instruction != null &&
                instruction.getAddress().getUnsignedOffset() <= end) {
            writeInstruction(output, instruction);
            instruction = instruction.getNext();
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflPoseMatrixApplyTrace.java OUTPUT_DIRECTORY");
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
                new File(directory, "nfl_pose_matrix_apply_trace.txt")))) {
            trace.write("NFL 2K5 sampled-pose-to-matrix focused trace\n");
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
            trace.write("\nRAW_CONTIGUOUS_RANGES\n");
            for (long[] range : RAW_RANGES) {
                trace.write("\n");
                writeRawRange(trace, range[0], range[1]);
            }
            trace.write("\nFOCUSED_FUNCTION_INSTRUCTIONS\n");
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
                new File(directory, "nfl_pose_matrix_apply_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 sampled-pose-to-matrix focused pseudo-C. */\n\n");
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
            pseudo.write("// PORTME: recover 0x0012F670 switch arms as structured C; the raw trace preserves every instruction.\n");
            pseudo.write("// PORTME: semantically recover and port every player-proportion adjustment in 0x00092140 and 0x00093850.\n");
            pseudo.write("// PORTME: model the inactive-coach guard without introducing portable-C uninitialized reads.\n");
            pseudo.write("// PORTME: prove which runtime object families exercise the direct full-pose builders during football gameplay.\n");
            pseudo.write("// PORTME: apply the proved XYZ/centimeter contract while preserving each builder's external-root and loop ownership.\n");
            pseudo.write("// PORTME: do not export player animation until 0x00092140/0x00093850 are value-equivalently ported; coach/referee local rotation export remains separately eligible.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_POSE_MATRIX_APPLY_TRACE_COMPLETE functions=" + functions.size());
    }
}
