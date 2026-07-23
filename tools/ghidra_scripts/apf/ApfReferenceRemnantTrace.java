// Emit focused read-only evidence for APF 2K8's registered REFR handler.
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
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfReferenceRemnantTrace extends GhidraScript {
    private static final long REFR_HASH = 0x15578F45L;
    private static final long DESCRIPTOR_START = 0x820FEAFCL;
    private static final long DESCRIPTOR_END = 0x820FEB10L;
    private static final long RUNTIME_NODE_START = 0x84EAB870L;
    private static final long RUNTIME_NODE_END = 0x84EAB8B0L;
    private static final long[] FUNCTIONS = {
        0x84AB0D58L, // REFR body pointer/record relocation worker
        0x84AB0FA8L, // REFR resource lookup/owner witness; reads CRC32("REFR")
        0x84AB10C0L, // REFR load/relocation callback
        0x84AB1110L, // runtime node link helper
        0x84AB1148L, // runtime node unlink helper
        0x84B1C710L, // shared callback
        0x84AB11A8L, // REFR destructor/list-unlink callback
        0x84B1C718L, // shared no-op callback
        0x84AB1270L, // registered fail-fast virtual-method witness
        0x84AB12E0L, // REFR runtime accessor witness
        0x84AB1320L  // REFR runtime accessor witness
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

    private Function ensureFunction(long value) throws Exception {
        Address entry = address(value);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function != null) return function;
        disassemble(entry);
        createFunction(entry, null);
        function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function == null) {
            throw new IllegalStateException("could not create transient function at " + hex(value));
        }
        return function;
    }

    private String asciiWord(long raw) {
        StringBuilder result = new StringBuilder();
        for (int shift = 24; shift >= 0; shift -= 8) {
            int value = (int)((raw >>> shift) & 0xff);
            result.append(value >= 0x20 && value <= 0x7e ? (char)value : '.');
        }
        return result.toString();
    }

    private void writeWindow(BufferedWriter writer, Memory memory, long start, long end)
            throws Exception {
        for (long value = start; value < end; value += 4) {
            Address slot = address(value);
            long raw = Integer.toUnsignedLong(memory.getInt(slot));
            writer.write(hex(value) + " raw=" + hex(raw) + " ascii=" + asciiWord(raw) +
                " refs=" + String.join(";", referencesTo(slot)) + "\n");
        }
    }

    private void writeFunctionInstructions(BufferedWriter writer, Function function)
            throws Exception {
        writer.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody().toString() + " refs=" +
            String.join(";", referencesTo(function.getEntryPoint())) + "\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            writer.write(hex(instruction.getAddress().getUnsignedOffset()) + " " +
                instruction.toString() + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
        writer.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfReferenceRemnantTrace.java OUTPUT_FILE");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5) &&
            !"c6f5639ac4c428682db0362947a223d8".equalsIgnoreCase(executableMd5) &&
            !"5370d49a9542d60c0345391e4e4aa656".equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }

        File output = new File(args[0]);
        File parent = output.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }
        Memory memory = currentProgram.getMemory();
        long descriptorHash = Integer.toUnsignedLong(memory.getInt(address(DESCRIPTOR_START)));
        long runtimeHash = Integer.toUnsignedLong(memory.getInt(address(RUNTIME_NODE_START + 4)));
        if (descriptorHash != REFR_HASH || runtimeHash != REFR_HASH) {
            throw new IllegalStateException(
                "REFR hash witnesses changed: " + hex(descriptorHash) + " / " + hex(runtimeHash));
        }

        Set<Function> focused = new LinkedHashSet<>();
        for (long value : FUNCTIONS) focused.add(ensureFunction(value));

        try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
            writer.write("APF 2K8 REFR/reference.iff focused static trace\n");
            writer.write("Program MD5: " + executableMd5 + "\n");
            writer.write("Program name: " + currentProgram.getName() + "\n");
            writer.write("Program language: " + currentProgram.getLanguageID() + "\n");
            writer.write("Constraint: registry/handler presence does not prove menu reachability.\n\n");

            writer.write("REFR_HASH_WITNESSES\n");
            writer.write(hex(DESCRIPTOR_START) + " value=" + hex(descriptorHash) +
                " expected=CRC32(REFR) refs=" +
                String.join(";", referencesTo(address(DESCRIPTOR_START))) + "\n");
            writer.write(hex(RUNTIME_NODE_START + 4) + " value=" + hex(runtimeHash) +
                " expected=CRC32(REFR) refs=" +
                String.join(";", referencesTo(address(RUNTIME_NODE_START + 4))) + "\n\n");

            writer.write("STATIC_DESCRIPTOR\n");
            writeWindow(writer, memory, DESCRIPTOR_START, DESCRIPTOR_END);
            writer.write("\nRUNTIME_NODE\n");
            writeWindow(writer, memory, RUNTIME_NODE_START, RUNTIME_NODE_END);

            writer.write("\nFOCUSED_FUNCTION_DISASSEMBLY\n");
            for (Function function : focused) writeFunctionInstructions(writer, function);

            DecompInterface decompiler = new DecompInterface();
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }
            try {
                writer.write("FOCUSED_PSEUDO_C\n");
                for (Function function : focused) {
                    writer.write("/* " + functionName(function) + " */\n");
                    DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                    if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                        writer.write(result.getDecompiledFunction().getC());
                    }
                    else {
                        String reason = result.isTimedOut() ? "timed out after 60 seconds" :
                            result.getErrorMessage();
                        writer.write("// PORTME: could not decompile function at " +
                            hex(function.getEntryPoint().getUnsignedOffset()) + "; " +
                            reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                    }
                    writer.write("\n");
                }
            }
            finally {
                decompiler.dispose();
            }
        }
        println("APF_REFERENCE_REMNANT_TRACE_COMPLETE functions=" + focused.size());
    }
}
