// Emit exact read-only evidence around unresolved NFL 2K5/APF 2K8 menu boundaries.
// @category VisualConcepts.Menu

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
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class MenuTraceClosure extends GhidraScript {
    private static final String NFL_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[][] NFL_RANGES = {
        {0x000F3E80L, 0x000F3FC0L},
        {0x002C8800L, 0x002C88C0L},
        {0x0014FC40L, 0x00150240L},
        {0x000F1D40L, 0x000F1E40L}
    };

    private static final long[] NFL_FOCUS = {
        0x000F3E90L, 0x002C8810L, 0x0014FC60L, 0x0014FDA0L,
        0x0014FF80L, 0x00150020L, 0x000F1D50L
    };

    private static final long[][] APF_RANGES = {
        {0x846EDE90L, 0x846EE0A0L},
        {0x846EE190L, 0x846EE520L},
        {0x846EF620L, 0x846EF7B0L},
        {0x846EFD20L, 0x846EFE20L},
        {0x846EFF70L, 0x846F0070L},
        {0x846F1760L, 0x846F1DE0L},
        {0x846F2DF0L, 0x846F30A0L},
        {0x846F3C90L, 0x846F4190L},
        {0x846F45D0L, 0x846F4790L},
        {0x846F4B80L, 0x846F51A0L},
        {0x846F55D0L, 0x846F5BD0L},
        {0x84A56960L, 0x84A56E40L},
        {0x84C77EB0L, 0x84C77F00L},
        {0x84CCB640L, 0x84CCB690L}
    };

    private static final long[] APF_FOCUS = {
        0x846F2E00L, 0x846F3CB0L, 0x846F40B8L, 0x846F45E0L,
        0x846F55E8L, 0x846F5840L, 0x846F59A8L,
        0x846F06F0L, 0x846F0708L, 0x846F4270L,
        0x846F1778L, 0x846F18A0L, 0x846EFF80L,
        0x846F3258L, 0x846F3728L, 0x846F3A58L, 0x846F3AC0L,
        0x846F5508L, 0x846F5518L, 0x846F56A8L,
        0x846F5C90L, 0x846F5E80L, 0x846F60E8L, 0x846F6100L,
        0x846F62E8L, 0x846F6618L, 0x846F8868L, 0x846F8B80L,
        0x846F8990L, 0x846F89C8L,
        0x846EFD38L, 0x846EE1A8L, 0x846EF638L, 0x846EF7A0L,
        0x846EDEA8L, 0x846EDFD0L, 0x846EDD30L,
        0x84B20E48L, 0x84B16398L, 0x84C559C0L,
        0x84A58698L
    };

    private static final long[] APF_REFERENCE_TARGETS = {
        0x820F4350L, 0x820F4354L, 0x8460C060L, 0x8460C088L,
        0x8450232CL, 0x846EDEA8L, 0x846EDFD0L, 0x846F40B8L,
        0x846F06F0L, 0x846F0708L, 0x846F4270L,
        0x846F2E00L, 0x846F45E0L, 0x846F59A8L, 0x846EFD38L,
        0x846EE1A8L, 0x846EF638L
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
        if (function == null) return "none";
        return hex(function.getEntryPoint()) + ":" + function.getName();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", value & 0xff));
        }
        return result.toString();
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

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private void writeTarget(BufferedWriter output, long value, Set<Function> functions)
            throws Exception {
        Address target = address(value);
        Function at = currentProgram.getFunctionManager().getFunctionAt(target);
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(target);
        if (owner != null) functions.add(owner);
        output.write(hex(value) + " section=" + section(target) +
            " function_at=" + functionName(at) + " owner=" + functionName(owner) +
            " refs=" + String.join(";", referencesTo(target)) + "\n");
    }

    private void writeRange(BufferedWriter output, long first, long afterLast,
            Set<Function> functions) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast - 1) + "\n");
        long value = first;
        while (value < afterLast) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                // This changes only the transient listing opened with -readOnly.  It neither
                // creates a function nor writes the project or executable.
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(value) + " <no instruction> // PORTME: inline data or " +
                    "decoder rejected the bytes\n");
                value += currentProgram.getLanguageID().getIdAsString().startsWith("PowerPC")
                    ? 4 : 1;
                continue;
            }
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            if (owner != null) functions.add(owner);
            output.write(hex(value) + " " + bytes(instruction) + " " + instruction +
                " owner=" + functionName(owner) + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
            value = instruction.getMaxAddress().getUnsignedOffset() + 1;
        }
        output.write("\n");
    }

    private void writeBytes(BufferedWriter output, long first, int count) throws Exception {
        byte[] data = new byte[count];
        Memory memory = currentProgram.getMemory();
        int read = memory.getBytes(address(first), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(first));
        StringBuilder text = new StringBuilder();
        for (byte value : data) text.append(String.format("%02x", value & 0xff));
        output.write(hex(first) + " length=" + count + " bytes=" + text + "\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: MenuTraceClosure.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        boolean nfl = NFL_MD5.equals(md5);
        boolean apf = APF_MD5.equals(md5);
        if (!nfl && !apf) throw new IllegalStateException("unexpected executable MD5 " + md5);

        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        String prefix = nfl ? "nfl" : "apf";
        long[][] ranges = nfl ? NFL_RANGES : APF_RANGES;
        long[] focus = nfl ? NFL_FOCUS : APF_FOCUS;
        Set<Function> functions = new LinkedHashSet<>();

        File traceFile = new File(directory, prefix + "_menu_trace_closure.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write((nfl ? "NFL 2K5" : "APF 2K8") +
                " menu-boundary read-only closure trace\n");
            trace.write("Program MD5: " + md5 + "\n");
            trace.write("Program SHA-256 provenance is enforced by the companion generator.\n");
            trace.write("No saved function, label, datatype, or program byte is created or changed; " +
                "transient disassembly is discarded by -readOnly.\n\n");

            trace.write("FOCUS\n");
            for (long value : focus) writeTarget(trace, value, functions);
            trace.write("\nREFERENCES\n");
            if (apf) {
                for (long value : APF_REFERENCE_TARGETS) writeTarget(trace, value, functions);
                trace.write("\nSTATIC_BYTES\n");
                writeBytes(trace, 0x820F4350L, 0x48);
                writeBytes(trace, 0x8460C060L, 0x28);
                writeBytes(trace, 0x8450232CL, 0x24);
            }
            else {
                for (long value : NFL_FOCUS) writeTarget(trace, value, functions);
                trace.write("\nSTATIC_BYTES\n");
                writeBytes(trace, 0x00515660L, 0x20);
            }
            trace.write("\nINSTRUCTIONS\n");
            for (long[] range : ranges) writeRange(trace, range[0], range[1], functions);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, prefix + "_menu_trace_closure_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* Saved-boundary pseudo-C; absent/over-merged boundaries stay PORTME. */\n\n");
            for (long value : focus) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                if (function == null) {
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; Ghidra has no saved function boundary at this entry.\n");
                }
            }
            pseudo.write("\n");
            for (Function function : sorted(functions)) {
                pseudo.write("/* " + functionName(function) + " body=" +
                    hex(function.getBody().getMinAddress()) + ".." +
                    hex(function.getBody().getMaxAddress()) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 60 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("MENU_TRACE_CLOSURE_COMPLETE platform=" + prefix +
            " saved_functions=" + functions.size());
    }
}
