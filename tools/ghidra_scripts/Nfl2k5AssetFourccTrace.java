// Trace NFL 2K5 scene/audio FourCC immediates and references.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5AssetFourccTrace extends GhidraScript {
    private static final Map<String, Long> TARGETS = new LinkedHashMap<>();
    static {
        // Values are x86 little-endian scalar interpretations of the ASCII bytes.
        TARGETS.put("SCNE", 0x454E4353L);
        TARGETS.put("SHAP", 0x50414853L);
        TARGETS.put("TSET", 0x54455354L);
        TARGETS.put("SKEL", 0x4C454B53L);
        TARGETS.put("AUDO", 0x4F445541L);
        TARGETS.put("MRKS", 0x534B524DL);
        TARGETS.put("SMCD", 0x44434D53L);
        TARGETS.put("MMCD", 0x44434D4DL);
        TARGETS.put("ABNK", 0x4B4E4241L);
        TARGETS.put("WBNK", 0x4B4E4257L);
    }

    private String addr(Address address) {
        if (address == null) return "";
        return address.isMemoryAddress() ?
            String.format("0x%08X", address.getUnsignedOffset()) : address.toString();
    }

    private String section(Address address) {
        MemoryBlock block = currentProgram.getMemory().getBlock(address);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        String namespace = function.getParentNamespace() == null ||
            function.getParentNamespace().isGlobal() ? "" :
            function.getParentNamespace().getName(true) + "::";
        return addr(function.getEntryPoint()) + ":" + namespace + function.getName();
    }

    private List<Address> findBytes(byte[] needle) throws Exception {
        List<Address> hits = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                cursor = hit.add(1);
            }
        }
        return hits;
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private String relations(Set<Function> functions) {
        List<String> result = new ArrayList<>();
        for (Function function : sorted(functions)) result.add(functionName(function));
        return String.join(";", result);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: Nfl2k5AssetFourccTrace.java OUTPUT_DIRECTORY");
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }
        File reportFile = new File(output, "asset_fourcc_trace.txt");
        File pseudoFile = new File(output, "asset_fourcc_candidate_pseudo_c.c");
        Set<Function> candidates = new LinkedHashSet<>();
        Map<String, Integer> rawCounts = new LinkedHashMap<>();
        Map<String, Integer> scalarCounts = new LinkedHashMap<>();
        for (String name : TARGETS.keySet()) scalarCounts.put(name, 0);

        try (BufferedWriter report = new BufferedWriter(new FileWriter(reportFile))) {
            report.write("NFL 2K5 scene/audio FourCC static trace\n");
            report.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            report.write("Constraint: a FourCC hit proves marker use only; subsystem roles remain provisional.\n\n");

            for (Map.Entry<String, Long> target : TARGETS.entrySet()) {
                String name = target.getKey();
                List<Address> hits = findBytes(name.getBytes(StandardCharsets.US_ASCII));
                rawCounts.put(name, hits.size());
                report.write("RAW_" + name + " count=" + hits.size() +
                    " scalar=" + String.format("0x%08X", target.getValue()) + "\n");
                for (Address hit : hits) {
                    Function containing = currentProgram.getFunctionManager().getFunctionContaining(hit);
                    if (containing != null) candidates.add(containing);
                    List<String> references = new ArrayList<>();
                    ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(hit);
                    while (iterator.hasNext()) {
                        Reference reference = iterator.next();
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                            reference.getFromAddress());
                        if (owner != null) candidates.add(owner);
                        references.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + ")");
                    }
                    report.write(addr(hit) + " section=" + section(hit) +
                        " containing=" + functionName(containing) +
                        " references=" + String.join(";", references) + "\n");
                }
                report.write("\n");
            }

            report.write("SCALAR_OPERAND_HITS\n");
            InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (!(object instanceof Scalar)) continue;
                        long value = ((Scalar) object).getUnsignedValue();
                        for (Map.Entry<String, Long> target : TARGETS.entrySet()) {
                            if (value != target.getValue()) continue;
                            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                                instruction.getAddress());
                            if (owner != null) candidates.add(owner);
                            scalarCounts.put(target.getKey(), scalarCounts.get(target.getKey()) + 1);
                            report.write(target.getKey() + " " + addr(instruction.getAddress()) +
                                " section=" + section(instruction.getAddress()) +
                                " instruction=" + instruction +
                                " owner=" + functionName(owner) + "\n");
                        }
                    }
                }
            }

            report.write("\nCOUNTS\n");
            for (String name : TARGETS.keySet()) {
                report.write(name + " raw=" + rawCounts.get(name) +
                    " scalar_operands=" + scalarCounts.get(name) + "\n");
            }
            report.write("\nCANDIDATE_FUNCTIONS count=" + candidates.size() + "\n");
            for (Function function : sorted(candidates)) {
                report.write(functionName(function) +
                    " section=" + section(function.getEntryPoint()) +
                    " range=" + addr(function.getBody().getMinAddress()) + "-" +
                    addr(function.getBody().getMaxAddress()) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + "\n");
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* FourCC candidate functions; recovered types and roles are provisional. */\n\n");
            for (Function function : sorted(candidates)) {
                pseudo.write("/* " + functionName(function) +
                    " section=" + section(function.getEntryPoint()) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 20, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 20 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        addr(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL2K5_ASSET_FOURCC_TRACE_COMPLETE candidates=" + candidates.size());
    }
}
