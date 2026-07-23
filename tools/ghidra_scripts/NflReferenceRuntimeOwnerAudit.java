// Read-only static ownership audit for NFL 2K5's reference-book UI strings.
// @category VisualConcepts.NFL

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
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
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflReferenceRuntimeOwnerAudit extends GhidraScript {
    private static final String NFL_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";
    private static final String[] TEXT = {
        "Reference Guide", "REFERENCEPLAYBOOK", "reference-pb.iff",
        "REFERENCE", "reference.iff", "reference_data", "closed_book", "open_book",
        "Play Terms", "Play Art", "Jargon", "Tips"
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private List<String> referencesTo(Address target, Set<Function> functions) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            if (owner != null) functions.add(owner);
            values.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        Collections.sort(values);
        return values;
    }

    private List<Address> find(byte[] needle, boolean aligned) throws Exception {
        List<Address> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                if (!aligned || (hit.getUnsignedOffset() & 3L) == 0) result.add(hit);
                cursor = hit.add(1);
            }
        }
        result.sort(Comparator.naturalOrder());
        return result;
    }

    private List<Address> pointerOccurrences(long value) throws Exception {
        byte[] little = {
            (byte)value, (byte)(value >>> 8), (byte)(value >>> 16), (byte)(value >>> 24)
        };
        // x86 absolute immediates begin one byte into PUSH/MOV opcodes and are
        // therefore commonly unaligned.
        return find(little, false);
    }

    private Function ensureFunction(long value) throws Exception {
        Address entry = address(value);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function != null) return function;
        disassemble(entry);
        createFunction(entry, null);
        function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function == null) throw new IllegalStateException("cannot create " + hex(value));
        return function;
    }

    private void writeWords(BufferedWriter output, long start, long end,
            Set<Function> functions) throws Exception {
        output.write("WINDOW " + hex(start) + ".." + hex(end) + "\n");
        Memory memory = currentProgram.getMemory();
        for (long value = start; value < end; value += 4) {
            Address cursor = address(value);
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            output.write(hex(value) + " raw=" + hex(raw) + " section=" +
                section(cursor) + " instruction=" +
                (instruction == null ? "<none>" : instruction.toString()) + " refs=" +
                String.join(";", referencesTo(cursor, functions)) + "\n");
        }
    }

    private void writeInstructions(BufferedWriter output, Function function,
            Set<Function> functions) throws Exception {
        output.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody() + " incoming=" + String.join(";",
                referencesTo(function.getEntryPoint(), functions)) + "\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " +
                instruction.toString() + " refs=" + String.join(";",
                    referencesTo(instruction.getAddress(), functions)) + "\n");
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException(
            "usage: NflReferenceRuntimeOwnerAudit.java OUTPUT_DIRECTORY");
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!NFL_MD5.equals(md5)) throw new IllegalStateException("unexpected NFL MD5 " + md5);
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> owners = new LinkedHashSet<>();
        owners.add(ensureFunction(0x003707C0L));
        owners.add(ensureFunction(0x003708B0L));
        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_reference_runtime_owner_trace.txt")))) {
            output.write("NFL 2K5 reference-book string ownership audit\n");
            output.write("Program MD5: " + md5 + "\n\n");
            for (String text : TEXT) {
                byte[] needle = text.getBytes(StandardCharsets.UTF_16LE);
                for (Address hit : find(needle, false)) {
                    output.write("TEXT " + text + " address=" +
                        hex(hit.getUnsignedOffset()) + " section=" + section(hit) +
                        " refs=" + String.join(";", referencesTo(hit, owners)) + "\n");
                    for (Address pointer : pointerOccurrences(hit.getUnsignedOffset())) {
                        Function owner = currentProgram.getFunctionManager()
                            .getFunctionContaining(pointer);
                        if (owner != null) owners.add(owner);
                        output.write("  POINTER " + hex(pointer.getUnsignedOffset()) +
                            " section=" + section(pointer) + " owner=" + functionName(owner) +
                            " refs=" + String.join(";", referencesTo(pointer, owners)) + "\n");
                    }
                }
            }
            output.write("\nREFERENCE_ROUTE\n");
            output.write("Extras row 0x005407D8 = {type 0, label 0x00EA48C4 " +
                "(Reference Guide), target descriptor 0x00583B18}.\n");
            output.write("Reference descriptor 0x00583B18 +4 -> event map 0x00583AE8; " +
                "event 1 -> action 0x00583A58 -> callback 0x003707C0; " +
                "event 2 -> action 0x00583AA0 -> callback 0x003708B0.\n");
            writeWords(output, 0x005407D8L, 0x0054080CL, owners);
            writeWords(output, 0x00583A58L, 0x00583AD0L, owners);
            writeWords(output, 0x00583AE8L, 0x00583B44L, owners);
            output.write("\nREFERENCE_FUNCTIONS\n");
            writeInstructions(output, ensureFunction(0x003707C0L), owners);
            writeInstructions(output, ensureFunction(0x003708B0L), owners);
        }

        List<Function> sorted = new ArrayList<>(owners);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException(
            "decompiler open failed");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_reference_runtime_owner_pseudo_c.c")))) {
            for (Function function : sorted) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    output.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint().getUnsignedOffset()) + "; " +
                        result.getErrorMessage().replace('\n', ' ') + "\n");
                }
                output.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_REFERENCE_RUNTIME_OWNER_AUDIT_COMPLETE owners=" + sorted.size());
    }
}
