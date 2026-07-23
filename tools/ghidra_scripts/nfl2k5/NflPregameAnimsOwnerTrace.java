// Read-only lifecycle/ownership trace for NFL 2K5 pregameanims.iff.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
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

public class NflPregameAnimsOwnerTrace extends GhidraScript {
    private static final String NFL_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";
    private static final String[] LITERALS = {
        "pregameanims.iff", "bigfigureafc", "bigfigurenfc", "bighelmet",
        "big_team_matchup"
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String owner(Address value) {
        Function function = currentProgram.getFunctionManager().getFunctionContaining(value);
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                owner(reference.getFromAddress()) + "," + reference.getReferenceType() + ")");
        }
        Collections.sort(result);
        return result;
    }

    private byte[] utf16le(String value) {
        byte[] text = value.getBytes(StandardCharsets.UTF_16LE);
        byte[] terminated = new byte[text.length + 2];
        System.arraycopy(text, 0, terminated, 0, text.length);
        return terminated;
    }

    private List<Address> findBytes(byte[] needle) throws Exception {
        List<Address> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(
                    cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                result.add(hit);
                cursor = hit.add(1);
            }
        }
        Collections.sort(result);
        return result;
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

    private void addReferenceOwners(Set<Function> functions, Address target) {
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Function function = currentProgram.getFunctionManager().getFunctionContaining(
                iterator.next().getFromAddress());
            if (function != null) functions.add(function);
        }
    }

    private void writeWindow(BufferedWriter output, long start, long end) throws Exception {
        Memory memory = currentProgram.getMemory();
        output.write("WINDOW " + hex(start) + ".." + hex(end) + "\n");
        for (long value = start; value < end; value += 4) {
            Address cursor = address(value);
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            MemoryBlock pointed = memory.getBlock(address(raw));
            output.write(hex(value) + " raw=" + hex(raw) + " points_to=" +
                (pointed == null ? "none" : pointed.getName()) + " refs=" +
                String.join(";", referencesTo(cursor)) + "\n");
        }
        output.write("\n");
    }

    private void writeFunction(BufferedWriter output, Function function) throws Exception {
        output.write("FUNCTION " + hex(function.getEntryPoint().getUnsignedOffset()) + ":" +
            function.getName() + " body=" + function.getBody() + " incoming=" +
            String.join(";", referencesTo(function.getEntryPoint())) + "\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " + instruction +
                " refs=" + String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException(
            "usage: NflPregameAnimsOwnerTrace.java OUTPUT_FILE");
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!NFL_MD5.equals(md5)) throw new IllegalStateException("unexpected NFL MD5 " + md5);

        Set<Function> focused = new LinkedHashSet<>();
        focused.add(ensureFunction(0x00125660L)); // resolve all three SCNE resources
        focused.add(ensureFunction(0x001256B0L)); // package callback bit 0
        focused.add(ensureFunction(0x001256C0L)); // package callback bit 1
        focused.add(ensureFunction(0x001256D0L)); // package callback bit 2
        focused.add(ensureFunction(0x00125700L)); // pregame package lifecycle initializer
        focused.add(ensureFunction(0x00125BC0L)); // pregame update/input owner
        focused.add(ensureFunction(0x00125C50L)); // package teardown/unload owner
        focused.add(ensureFunction(0x00125CD0L)); // transition release owner
        File outputFile = new File(args[0]);
        File parent = outputFile.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(outputFile))) {
            output.write("NFL_PREGAMEANIMS_OWNER_TRACE_V1\n");
            output.write("PROGRAM_MD5 " + md5 + "\n");
            output.write("READ_ONLY true\n\n");
            for (String literal : LITERALS) {
                List<Address> hits = findBytes(utf16le(literal));
                output.write("LITERAL " + literal + " encoding=UTF16LE hits=" + hits.size());
                for (Address hit : hits) {
                    output.write(" " + hex(hit.getUnsignedOffset()) + "[" +
                        String.join(";", referencesTo(hit)) + "]");
                    addReferenceOwners(focused, hit);
                }
                output.write("\n");
            }
            output.write("\n");

            // The exact package loader and the static big_team_matchup descriptor.
            writeWindow(output, 0x001257D0L, 0x00125880L);
            writeWindow(output, 0x00AAD6C0L, 0x00AAD760L);

            List<Function> sorted = new ArrayList<>(focused);
            sorted.sort((a, b) -> a.getEntryPoint().compareTo(b.getEntryPoint()));
            output.write("FOCUSED_FUNCTIONS count=" + sorted.size() + "\n");
            for (Function function : sorted) writeFunction(output, function);

            DecompInterface decompiler = new DecompInterface();
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }
            try {
                output.write("PSEUDO_C\n");
                for (Function function : sorted) {
                    output.write("/* " + hex(function.getEntryPoint().getUnsignedOffset()) + ":" +
                        function.getName() + " */\n");
                    DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                    output.write(result.decompileCompleted()
                        ? result.getDecompiledFunction().getC()
                        : "// decompile failed: " + result.getErrorMessage() + "\n");
                    output.write("\n");
                }
            }
            finally {
                decompiler.dispose();
            }
        }
        println("NFL pregameanims ownership trace written to " + outputFile);
    }
}
