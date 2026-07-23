// Emit focused static evidence for APF 2K8 uniform/logo resource selection.
// @category Xbox360.APF2K8

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
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfUniformTrace extends GhidraScript {
    private static final long[] TEMPLATE_ADDRESSES = {
        0x845F1B14L, 0x845F1B44L, 0x845F1B78L, 0x845F1BA8L,
        0x845F1BD8L, 0x845F1C0CL, 0x845F1C44L, 0x845F1C74L,
        0x845F1CA8L, 0x845F1CDCL, 0x845F1D10L, 0x845F1D48L,
        0x845F1D90L, 0x845F1DBCL
    };
    private static final long[] FOCUSED_FUNCTIONS = {
        0x8467C978L, // frontend registration of uniform_logocache.iff
        0x84688690L, // LOGOS / logo%s selector
        0x846826E8L, // installs the first active team record
        0x84682750L, // installs the second active team record
        0x84687D88L, // pointer-array accessor used by the selector
        0x8470F6A0L, // obtains and installs the two active ROST team records
        0x84746F78L, // ROST team index -> record at stride 0x180
        0x849D6B18L, // one team-indexed filename selector
        0x849D6BD0L, // uniform filename selector switch
        0x849D6E48L, // team player-slot filename selector
        0x849D6F68L, // {0}.iff formatter
        0x84AF4DD0L  // logo_%s_0 TXTR lookup
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
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            values.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        values.sort(String::compareTo);
        return values;
    }

    private String readUtf16Be(long value) throws Exception {
        Memory memory = currentProgram.getMemory();
        Address cursor = address(value);
        StringBuilder result = new StringBuilder();
        for (int count = 0; count < 256; count++) {
            int codeUnit = Short.toUnsignedInt(memory.getShort(cursor));
            if (codeUnit == 0) return result.toString();
            result.append((char)codeUnit);
            cursor = cursor.add(2);
        }
        throw new IllegalStateException("unterminated UTF-16BE string at " + hex(value));
    }

    private Function ensureFunction(long value) throws Exception {
        Address entry = address(value);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function != null) return function;
        disassemble(entry);
        createFunction(entry, null);
        return currentProgram.getFunctionManager().getFunctionAt(entry);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfUniformTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5) &&
            !"c6f5639ac4c428682db0362947a223d8".equalsIgnoreCase(executableMd5) &&
            !"5370d49a9542d60c0345391e4e4aa656".equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }

        Set<Function> focused = new LinkedHashSet<>();
        File traceFile = new File(output, "uniform_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 uniform/logo focused static trace\n");
            trace.write("Program MD5: " + executableMd5 + "\n");
            trace.write("Program name: " + currentProgram.getName() + "\n");
            trace.write("Program language: " + currentProgram.getLanguageID() + "\n\n");
            trace.write("UTF16BE_TEMPLATES\n");
            for (long value : TEMPLATE_ADDRESSES) {
                Address target = address(value);
                trace.write(hex(value) + " value=" + readUtf16Be(value) +
                    " refs=" + String.join(";", referencesTo(target)) + "\n");
            }
            trace.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED_FUNCTIONS) {
                Function function = ensureFunction(value);
                trace.write(hex(value) + " " + functionName(function) +
                    " refs=" + String.join(";", referencesTo(address(value))) + "\n");
                if (function != null) focused.add(function);
            }
            trace.write("\nACCESSOR_DISASSEMBLY\n");
            for (long base : new long[] {0x84687D78L, 0x84687D80L,
                                         0x84687D88L, 0x847080C8L}) {
                Address cursor = address(base);
                for (int count = 0; count < 6; count++) {
                    Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
                    if (instruction == null) {
                        disassemble(cursor);
                        instruction = currentProgram.getListing().getInstructionAt(cursor);
                    }
                    if (instruction == null) {
                        trace.write(hex(cursor.getUnsignedOffset()) +
                            " PORTME: could not disassemble accessor instruction\n");
                        break;
                    }
                    trace.write(hex(cursor.getUnsignedOffset()) + " " +
                        instruction.toString() + "\n");
                    if ("blr".equals(instruction.getMnemonicString())) break;
                    cursor = instruction.getMaxAddress().add(1);
                }
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "uniform_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF 2K8 uniform/logo focused pseudo-C. */\n\n");
            for (Function function : focused) {
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
    }
}
