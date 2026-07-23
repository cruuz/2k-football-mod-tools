// Trace NFL 2K5 TXTR/FEEDBEEF references and decompile candidate handlers.
// @category Xbox.NFL2K5

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
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5TxtrTrace extends GhidraScript {
    private static final long TXTR_SCALAR = 0x52545854L; // x86 little-endian immediate for bytes "TXTR"
    private static final long FEEDBEEF = 0xFEEDBEEFL;

    private String addr(Address address) {
        if (address == null) return "";
        return address.isMemoryAddress() ? String.format("0x%08X", address.getUnsignedOffset()) : address.toString();
    }

    private String section(Address address) {
        MemoryBlock block = currentProgram.getMemory().getBlock(address);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        String ns = function.getParentNamespace() == null || function.getParentNamespace().isGlobal() ?
            "" : function.getParentNamespace().getName(true) + "::";
        return addr(function.getEntryPoint()) + ":" + ns + function.getName();
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
        List<String> values = new ArrayList<>();
        for (Function function : sorted(functions)) values.add(functionName(function));
        return String.join(";", values);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("usage: Nfl2k5TxtrTrace.java OUTPUT_DIRECTORY");
        File out = new File(args[0]);
        if (!out.isDirectory() && !out.mkdirs()) throw new IllegalStateException("cannot create " + out);

        File reportFile = new File(out, "txtr_feedbeef_trace.txt");
        File pseudoFile = new File(out, "txtr_candidate_pseudo_c.c");
        List<Address> txtrHits = findBytes(new byte[] {0x54, 0x58, 0x54, 0x52});
        List<Address> feedHits = findBytes(new byte[] {(byte)0xEF, (byte)0xBE, (byte)0xED, (byte)0xFE});
        Set<Function> candidates = new LinkedHashSet<>();

        try (BufferedWriter report = new BufferedWriter(new FileWriter(reportFile))) {
            report.write("NFL 2K5 TXTR / FEEDBEEF static trace\n");
            report.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            report.write("Constants: ASCII TXTR bytes 54 58 54 52; x86 scalar 0x52545854; scalar 0xFEEDBEEF.\n\n");
            report.write("RAW_TXTR_HITS count=" + txtrHits.size() + "\n");
            for (Address hit : txtrHits) {
                Function containing = currentProgram.getFunctionManager().getFunctionContaining(hit);
                if (containing != null) candidates.add(containing);
                report.write(addr(hit) + " section=" + section(hit) + " containing=" + functionName(containing));
                List<String> refs = new ArrayList<>();
                ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(hit);
                while (iterator.hasNext()) {
                    Reference reference = iterator.next();
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
                    if (owner != null) candidates.add(owner);
                    refs.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + ")");
                }
                report.write(" references=" + String.join(";", refs) + "\n");
            }

            report.write("\nRAW_FEEDBEEF_LE_HITS count=" + feedHits.size() + "\n");
            for (Address hit : feedHits) {
                Function containing = currentProgram.getFunctionManager().getFunctionContaining(hit);
                if (containing != null) candidates.add(containing);
                report.write(addr(hit) + " section=" + section(hit) + " containing=" + functionName(containing));
                List<String> refs = new ArrayList<>();
                ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(hit);
                while (iterator.hasNext()) {
                    Reference reference = iterator.next();
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
                    if (owner != null) candidates.add(owner);
                    refs.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + ")");
                }
                report.write(" references=" + String.join(";", refs) + "\n");
            }

            report.write("\nSCALAR_OPERAND_HITS\n");
            InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (!(object instanceof Scalar)) continue;
                        long value = ((Scalar)object).getUnsignedValue();
                        if (value != TXTR_SCALAR && value != FEEDBEEF) continue;
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(instruction.getAddress());
                        if (owner != null) candidates.add(owner);
                        report.write(addr(instruction.getAddress()) + " section=" + section(instruction.getAddress()) +
                            " scalar=" + String.format("0x%08X", value) + " instruction=" + instruction +
                            " owner=" + functionName(owner) + "\n");
                    }
                }
            }

            report.write("\nCANDIDATE_FUNCTIONS count=" + candidates.size() + "\n");
            for (Function function : sorted(candidates)) {
                report.write(functionName(function) + " section=" + section(function.getEntryPoint()) +
                    " range=" + addr(function.getBody().getMinAddress()) + "-" + addr(function.getBody().getMaxAddress()) +
                    " size=" + function.getBody().getNumAddresses() + " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + "\n");
            }
            report.write("\nInterpretation constraint: a constant/reference match proves use of the marker, not by itself whether the function performs file I/O, header validation, allocation, or decompression. Inspect pseudo-C and callers before naming it.\n");
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException("decompiler could not open program");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* Candidate TXTR/FEEDBEEF functions. Types and names are provisional. */\n\n");
            for (Function function : sorted(candidates)) {
                pseudo.write("/* " + functionName(function) + " section=" + section(function.getEntryPoint()) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 30 seconds" : result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + addr(function.getEntryPoint()) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL2K5_TXTR_TRACE_COMPLETE txtr_hits=" + txtrHits.size() + " feedbeef_hits=" + feedHits.size() +
            " candidate_functions=" + candidates.size());
    }
}
