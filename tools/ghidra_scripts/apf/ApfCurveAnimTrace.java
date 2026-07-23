// Emit focused static evidence for APF 2K8 CurveAnim resources.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
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
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfCurveAnimTrace extends GhidraScript {
    private static final long CURVE_ANIM_HASH = 0xF4257702L;
    private static final long[] FOCUSED_FUNCTIONS = {
        0x84667B08L, // resource-type node constructor entry
        0x846684B0L, // four-pointer inverse serializer helper
        0x84668528L, // four-pointer load relocator helper
        0x84668C00L, // registered CurveAnim load callback
        0x84668C50L, // registered CurveAnim inverse callback
        0x84668F40L, // registered destructor/list unlink callback
        0x849CD578L, // type-hash lookup and DRAM-part selection
        0x849CD710L, // two-registry lookup wrapper
        0x84AAA310L  // caller retaining the selected CurveAnim resource
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String addr(Address value) {
        if (value == null) return "";
        return value.isMemoryAddress() ?
            String.format("0x%08X", value.getUnsignedOffset()) : value.toString();
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<Address> findBytes(byte[] needle) throws Exception {
        List<Address> hits = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(
                    cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                cursor = hit.add(1);
            }
        }
        return hits;
    }

    private List<String> referencesTo(Address target, Set<Function> candidates) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            if (owner != null) candidates.add(owner);
            values.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        values.sort(String::compareTo);
        return values;
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private void writeWindow(BufferedWriter report, Address center) throws Exception {
        Memory memory = currentProgram.getMemory();
        Address first = center.subtract(0x40);
        Address last = center.add(0x40);
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            if (!memory.contains(cursor)) continue;
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            report.write(addr(cursor) + " raw=" + String.format("0x%08X", raw) + "\n");
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfCurveAnimTrace.java OUTPUT_DIRECTORY");
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

        Set<Function> candidates = new LinkedHashSet<>();
        List<Address> hashHits = findBytes(new byte[] {
            (byte)0xF4, 0x25, 0x77, 0x02
        });
        List<Address> nameHits = findBytes("CurveAnim".getBytes(StandardCharsets.US_ASCII));
        for (long value : FOCUSED_FUNCTIONS) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function != null) candidates.add(function);
        }
        File reportFile = new File(output, "curve_anim_trace.txt");
        try (BufferedWriter report = new BufferedWriter(new FileWriter(reportFile))) {
            report.write("APF 2K8 CurveAnim focused static trace\n");
            report.write("Program MD5: " + executableMd5 + "\n");
            report.write("Program name: " + currentProgram.getName() + "\n");
            report.write("Program language: " + currentProgram.getLanguageID() + "\n");
            report.write("Constraint: fields remain opaque unless direct consumers prove them.\n\n");

            report.write("CURVE_ANIM_HASH 0xF4257702 raw_hits=" + hashHits.size() + "\n");
            for (Address hit : hashHits) {
                MemoryBlock block = currentProgram.getMemory().getBlock(hit);
                Function containing = currentProgram.getFunctionManager().getFunctionContaining(hit);
                if (containing != null) candidates.add(containing);
                report.write(addr(hit) + " block=" +
                    (block == null ? "none" : block.getName()) + " containing=" +
                    functionName(containing) + " refs=" +
                    String.join(";", referencesTo(hit, candidates)) + "\n");
                writeWindow(report, hit);
            }

            report.write("\nCURVE_ANIM_ASCII raw_hits=" + nameHits.size() + "\n");
            for (Address hit : nameHits) {
                Function containing = currentProgram.getFunctionManager().getFunctionContaining(hit);
                if (containing != null) candidates.add(containing);
                report.write(addr(hit) + " containing=" + functionName(containing) +
                    " refs=" + String.join(";", referencesTo(hit, candidates)) + "\n");
            }

            report.write("\nIMMEDIATE_HITS\n");
            InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                boolean matched = false;
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (!(object instanceof Scalar)) continue;
                        long value = ((Scalar)object).getUnsignedValue();
                        if (value == CURVE_ANIM_HASH || value == 0xF425L || value == 0x7702L) {
                            matched = true;
                        }
                    }
                }
                if (!matched) continue;
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                    instruction.getAddress());
                report.write(addr(instruction.getAddress()) + " instruction=" + instruction +
                    " owner=" + functionName(owner) + "\n");
            }

            report.write("\nCANDIDATE_FUNCTIONS count=" + candidates.size() + "\n");
            for (Function function : sorted(candidates)) {
                report.write(functionName(function) + "\n");
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "curve_anim_candidate_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF 2K8 CurveAnim candidate pseudo-C. */\n\n");
            for (Function function : sorted(candidates)) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 60 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        String.format("0x%08X", value) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_CURVE_ANIM_TRACE_COMPLETE hash_hits=" + hashHits.size() +
            " name_hits=" + nameHits.size() + " candidates=" + candidates.size());
    }
}
