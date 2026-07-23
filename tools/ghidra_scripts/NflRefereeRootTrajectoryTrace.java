// Emit focused NFL 2K5 gameplay-referee trajectory ownership evidence.
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

public class NflRefereeRootTrajectoryTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x000DEE30L, 0x000DF3D0L,
        0x00096600L, 0x00096B20L,
        0x00217D00L, 0x00217EB0L, 0x00218010L, 0x002180D0L,
        0x002406E0L,
        0x002D6950L, 0x002D6B70L,
        0x002CC470L, 0x002CC570L,
        0x00318310L,
        0x0031B2E0L, 0x0031B4E0L, 0x0031BEB0L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace()
            .getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String functionName(Function function) {
        return function == null ? "none" :
            hex(function.getEntryPoint().getUnsignedOffset()) + ":" +
            function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator =
            currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager()
                .getFunctionContaining(reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) +
                "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private void writeFunctionInstructions(BufferedWriter output,
            Function function) throws Exception {
        Instruction instruction = currentProgram.getListing()
            .getInstructionAt(function.getEntryPoint());
        while (instruction != null &&
               function.getBody().contains(instruction.getAddress())) {
            output.write(hex(instruction.getAddress().getUnsignedOffset()) +
                " " + instruction + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) +
                "\n");
            instruction = instruction.getNext();
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflRefereeRootTrajectoryTrace.java OUTPUT_DIRECTORY");
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
                new File(directory,
                    "nfl_referee_root_trajectory_trace.txt")))) {
            trace.write("NFL 2K5 gameplay-referee root/trajectory focused trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() +
                "\n\nKEY_REFERENCES\n");
            long[] targets = {
                0x000DF3D0L, 0x00217EB0L, 0x00218010L, 0x002180D0L,
                0x002406E0L, 0x002D6B70L, 0x002CC570L,
                0x0031B2E0L, 0x0031B4E0L, 0x0031BEB0L,
                0x0051D010L, 0x00E60274L
            };
            for (long target : targets) {
                trace.write(hex(target) + " refs=" +
                    String.join(";", referencesTo(address(target))) + "\n");
            }
            trace.write("\nFOCUSED_FUNCTION_REFERENCES\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                trace.write(hex(value) + " " + functionName(function) +
                    " refs=" +
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
                new File(directory,
                    "nfl_referee_root_trajectory_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 gameplay-referee trajectory focused pseudo-C. */\n\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result =
                    decompiler.decompileFunction(function, 240, monitor);
                if (result.decompileCompleted() &&
                    result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ?
                        "timed out after 240 seconds" : result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        hex(value) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
            pseudo.write("// PORTME: prove the selected dynamic one-of-seven actor record before assigning a concrete gameplay initial transform.\n");
            pseudo.write("// PORTME: retain actor scale and heading/facing inputs; the callback does not apply raw clip-local X/Z directly.\n");
            pseudo.write("// PORTME: join the actor transform pointer at +0x18 to the final referee render external-root consumer before emitting a gameplay-equivalent glTF root track.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_REFEREE_ROOT_TRAJECTORY_TRACE_COMPLETE functions=" +
            functions.size());
    }
}
