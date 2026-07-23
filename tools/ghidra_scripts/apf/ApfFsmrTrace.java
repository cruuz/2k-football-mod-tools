// Emit focused static evidence for APF 2K8's sole FSMR resource.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ApfFsmrTrace extends GhidraScript {
    private static final long REGISTRY_START = 0x820D2B40L;
    private static final long REGISTRY_END = 0x820D2C20L;
    private static final long FSMR_HASH_ADDRESS = 0x820D2B74L;
    private static final long[] CALLBACKS = {
        0x84979058L, 0x84979100L, 0x849791B0L, 0x84B1C718L
    };
    // The decompressed XEX payload is a memory image: section bytes live at
    // VirtualAddress, not PointerToRawData.  These addresses deliberately use
    // the XEX/runtime mapping and must not be shifted by PE raw-file deltas.
    private static final long FSMR_NODE_CONSTRUCTOR = 0x8467D1B8L;
    private static final long CROWD_RESOURCE_CONSUMER = 0x84975E60L;
    private static final long CROWD_RESOURCE_DECOMPILE_START = 0x84975E68L;
    private static final long CROWD_RESOURCE_TAIL_START = 0x84975F44L;
    private static final long CROWD_RESOURCE_CONSUMER_END = 0x84976073L;
    private static final long FSMR_EVALUATOR_TRUE_ENTRY = 0x84758DC8L;
    private static final long FSMR_EVALUATOR_BODY_ENTRY = 0x84758DD8L;
    private static final long FSMR_EVALUATOR_END = 0x84759147L;
    private static final Map<String, Long> CROWD_STRINGS = new LinkedHashMap<>();
    static {
        CROWD_STRINGS.put("Excessive crowd noise", 0x845ECBC0L);
        CROWD_STRINGS.put("Crowd_AllocateAndComputeAnimations", 0x845EDA08L);
        CROWD_STRINGS.put("Crowd_DrawCards", 0x845EDA50L);
        CROWD_STRINGS.put("Crowd_DrawAll", 0x845EDA70L);
        CROWD_STRINGS.put("DrawCrowdAfterPreProcess", 0x845EDA8CL);
        CROWD_STRINGS.put("Crowd Volume", 0x84604B24L);
        CROWD_STRINGS.put("CrowdShirtColors[data-a]", 0x84E26558L);
        CROWD_STRINGS.put("CrowdShirtColors[data-b]", 0x84E26EC8L);
    }

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

    private Set<Function> referenceOwners(Address target) {
        Set<Function> owners = new LinkedHashSet<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            if (owner != null) owners.add(owner);
        }
        return owners;
    }

    private String asciiWord(long raw) {
        StringBuilder value = new StringBuilder();
        for (int shift = 24; shift >= 0; shift -= 8) {
            int c = (int)((raw >>> shift) & 0xff);
            value.append(c >= 0x20 && c <= 0x7e ? (char)c : '.');
        }
        return value.toString();
    }

    private Function ensureFunction(long value) throws Exception {
        Address entry = address(value);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function != null) return function;
        disassemble(entry);
        createFunction(entry, null);
        return currentProgram.getFunctionManager().getFunctionAt(entry);
    }

    private List<Function> rebuildCrowdConsumer() throws Exception {
        Address start = address(CROWD_RESOURCE_CONSUMER);
        Address end = address(CROWD_RESOURCE_CONSUMER_END);
        List<Function> remove = new ArrayList<>();
        Function containing = currentProgram.getFunctionManager().getFunctionContaining(start);
        if (containing != null) remove.add(containing);
        FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(start, true);
        while (iterator.hasNext()) {
            Function function = iterator.next();
            if (function.getEntryPoint().compareTo(end) > 0) break;
            if (!remove.contains(function)) remove.add(function);
        }
        for (Function function : remove) {
            currentProgram.getFunctionManager().removeFunction(function.getEntryPoint());
        }
        clearListing(start, end);
        Address cursor = start;
        while (cursor.compareTo(end) <= 0) {
            disassemble(cursor);
            cursor = cursor.add(4);
        }
        // The real entry's first branch-with-link invokes an out-of-line save
        // helper.  Ghidra models that compiler helper as terminal.  Preserve
        // the true entry in the disassembly, but start the transient C body at
        // +8 so the remaining bounded instructions can be decompiled.
        Address decompileStart = address(CROWD_RESOURCE_DECOMPILE_START);
        Address tailStart = address(CROWD_RESOURCE_TAIL_START);
        Function randomHelper = currentProgram.getFunctionManager().getFunctionAt(
            address(0x84B3E8B8L));
        if (randomHelper != null) randomHelper.setNoReturn(false);
        Function head = currentProgram.getListing().createFunction(
            "FSMR_CrowdResourceConsumer_Body", decompileStart,
            new AddressSet(decompileStart, tailStart.subtract(1)),
            SourceType.ANALYSIS);
        Function tail = currentProgram.getListing().createFunction(
            "FSMR_CrowdResourceConsumer_Tail", tailStart,
            new AddressSet(tailStart, end), SourceType.ANALYSIS);
        List<Function> result = new ArrayList<>();
        result.add(head);
        result.add(tail);
        return result;
    }

    private Function rebuildEvaluatorBody() throws Exception {
        Address trueEntry = address(FSMR_EVALUATOR_TRUE_ENTRY);
        Address bodyEntry = address(FSMR_EVALUATOR_BODY_ENTRY);
        Address end = address(FSMR_EVALUATOR_END);
        List<Function> remove = new ArrayList<>();
        Function containing = currentProgram.getFunctionManager().getFunctionContaining(trueEntry);
        if (containing != null) remove.add(containing);
        FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(trueEntry, true);
        while (iterator.hasNext()) {
            Function function = iterator.next();
            if (function.getEntryPoint().compareTo(end) > 0) break;
            if (!remove.contains(function)) remove.add(function);
        }
        for (Function function : remove) {
            currentProgram.getFunctionManager().removeFunction(function.getEntryPoint());
        }
        clearListing(trueEntry, end);
        Address cursor = trueEntry;
        while (cursor.compareTo(end) <= 0) {
            disassemble(cursor);
            cursor = cursor.add(4);
        }
        return currentProgram.getListing().createFunction(
            "FSMR_TableEvaluator_Body", bodyEntry, new AddressSet(bodyEntry, end),
            SourceType.ANALYSIS);
    }

    private void writeInstructions(BufferedWriter trace, long first, long afterLast)
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
                trace.write(hex(cursor.getUnsignedOffset()) + " <no instruction>\n");
                cursor = cursor.add(4);
            }
            else {
                trace.write(hex(cursor.getUnsignedOffset()) + " " + instruction.toString() +
                    " refs=" + String.join(";", referencesTo(cursor)) + "\n");
                cursor = instruction.getMaxAddress().add(1);
            }
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfFsmrTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5) &&
            !"c6f5639ac4c428682db0362947a223d8".equalsIgnoreCase(executableMd5) &&
            !"5370d49a9542d60c0345391e4e4aa656".equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " +
                executableMd5);
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }

        Memory memory = currentProgram.getMemory();
        File traceFile = new File(output, "fsmr_trace.txt");
        Set<Function> focused = new LinkedHashSet<>();

        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 FSMR focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Program name: " + currentProgram.getName() + "\n");
            trace.write("Program language: " + currentProgram.getLanguageID() + "\n");
            trace.write("Constraint: resource fields remain unknown unless a direct consumer proves them.\n\n");

            trace.write("FSMR_REGISTRY_WINDOW\n");
            for (long value = REGISTRY_START; value < REGISTRY_END; value += 4) {
                Address slot = address(value);
                long raw = Integer.toUnsignedLong(memory.getInt(slot));
                trace.write(hex(value) + " raw=" + hex(raw) + " ascii=" + asciiWord(raw) +
                    " refs=" + String.join(";", referencesTo(slot)) + "\n");
            }
            trace.write("hash_address=" + hex(FSMR_HASH_ADDRESS) +
                " hash_value=" + hex(Integer.toUnsignedLong(memory.getInt(address(FSMR_HASH_ADDRESS)))) +
                " refs=" + String.join(";", referencesTo(address(FSMR_HASH_ADDRESS))) + "\n\n");

            trace.write("CALLBACKS\n");
            for (long value : CALLBACKS) {
                Function function = ensureFunction(value);
                if (function != null) focused.add(function);
                trace.write(hex(value) + " " + functionName(function) +
                    " refs=" + String.join(";", referencesTo(address(value))) + "\n");
            }
            List<Function> consumers = rebuildCrowdConsumer();
            if (consumers.isEmpty()) {
                trace.write(hex(CROWD_RESOURCE_CONSUMER) +
                    " PORTME: failed to reconstruct crowd resource consumer\n");
            }
            else {
                focused.addAll(consumers);
                trace.write(hex(CROWD_RESOURCE_CONSUMER) + " true_entry; " +
                    functionName(consumers.get(0)) + " body_entry_after_shared_save_helper; " +
                    functionName(consumers.get(1)) + " tail_entry_after_random_helper; " +
                    "reconstructed_transiently=true\n");
            }
            Function countedTableInitializer = ensureFunction(0x84759478L);
            if (countedTableInitializer != null) focused.add(countedTableInitializer);
            Function evaluator = rebuildEvaluatorBody();
            if (evaluator != null) {
                focused.add(evaluator);
                trace.write(hex(FSMR_EVALUATOR_TRUE_ENTRY) + " true_entry; " +
                    functionName(evaluator) + " body_entry_after_shared_save_helper; " +
                    "reconstructed_transiently=true\n");
            }

            trace.write("\nCROWD_STRING_REFERENCES\n");
            for (Map.Entry<String, Long> item : CROWD_STRINGS.entrySet()) {
                Address target = address(item.getValue());
                trace.write(hex(item.getValue()) + " label=" + item.getKey() +
                    " refs=" + String.join(";", referencesTo(target)) + "\n");
                focused.addAll(referenceOwners(target));
            }

            trace.write("\nUNRECOVERED_CALLBACK_DISASSEMBLY\n");
            writeInstructions(trace, 0x84B1C718L, 0x84B1C71CL);
            trace.write("\nFSMR_NODE_CONSTRUCTOR_DISASSEMBLY\n");
            writeInstructions(trace, FSMR_NODE_CONSTRUCTOR, 0x8467D1E4L);
            trace.write("\nCROWD_RESOURCE_CONSUMER_DISASSEMBLY\n");
            writeInstructions(trace, CROWD_RESOURCE_CONSUMER,
                CROWD_RESOURCE_CONSUMER_END + 1);
        }

        List<Function> sorted = new ArrayList<>(focused);
        sorted.sort((left, right) -> left.getEntryPoint().compareTo(right.getEntryPoint()));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "fsmr_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF 2K8 FSMR focused pseudo-C; unknown fields are intentionally unnamed. */\n\n");
            for (Function function : sorted) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " references=" +
                    String.join(";", referencesTo(function.getEntryPoint())) + " */\n");
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
        println("APF_FSMR_TRACE_COMPLETE functions=" + sorted.size());
    }
}
