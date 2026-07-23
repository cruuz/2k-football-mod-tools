// Read-only static ownership audit for APF 2K8's pregameanims.iff remnant.
// @category Xbox360.APF2K8

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

public class ApfPregameAnimsOwnerTrace extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final String[] LITERALS = {
        "pregameanims.iff", "bigfigureafc", "bigfigurenfc", "bighelmet",
        "big_team_matchup"
    };

    private static final long[][] HASHES = {
        {0x27B28292L, 0}, // CRC32 uppercase ASCII pregameanims.iff
        {0x73DEC7A1L, 1}, // CRC32 lowercase ASCII bigfigureafc
        {0x7882809CL, 2}, // CRC32 lowercase ASCII bigfigurenfc
        {0xDE413B72L, 3}, // CRC32 lowercase ASCII bighelmet
        {0xF0BD9799L, 4}, // CRC32 lowercase ASCII big_team_matchup
        {0xC6ED33A2L, 5}, // CRC32 uppercase ASCII MRKS
        {0xE26C9B5DL, 6}  // CRC32 uppercase ASCII SCNE
    };

    private static final String[] HASH_LABELS = {
        "pregameanims_iff", "bigfigureafc_resource_id",
        "bigfigurenfc_resource_id", "bighelmet_resource_id",
        "big_team_matchup_resource_id", "MRKS_type", "SCNE_type"
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

    private List<Address> findBytes(byte[] needle, boolean aligned) throws Exception {
        List<Address> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(
                    cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                if (!aligned || (hit.getUnsignedOffset() & 3L) == 0) result.add(hit);
                cursor = hit.add(1);
            }
        }
        Collections.sort(result);
        return result;
    }

    private byte[] utf16be(String value) {
        byte[] text = value.getBytes(StandardCharsets.UTF_16BE);
        byte[] terminated = new byte[text.length + 2];
        System.arraycopy(text, 0, terminated, 0, text.length);
        return terminated;
    }

    private List<Address> wordHits(long value) throws Exception {
        return findBytes(new byte[] {
            (byte)(value >>> 24), (byte)(value >>> 16),
            (byte)(value >>> 8), (byte)value
        }, true);
    }

    private List<String> materializations(long target) throws Exception {
        List<String> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        long wanted = target & 0xffffffffL;
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) continue;
            long first = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
            long last = block.getEnd().getUnsignedOffset();
            for (long value = first; value + 3 <= last; value += 4) {
                long raw = Integer.toUnsignedLong(memory.getInt(address(value)));
                if ((raw >>> 26) != 15 || ((raw >>> 16) & 31) != 0) continue;
                int register = (int)((raw >>> 21) & 31);
                long high = ((long)(short)(raw & 0xffffL) << 16) & 0xffffffffL;
                for (int distance = 1; distance <= 16; distance++) {
                    long site = value + 4L * distance;
                    if (site + 3 > last) break;
                    long next = Integer.toUnsignedLong(memory.getInt(address(site)));
                    int opcode = (int)(next >>> 26);
                    long computed = -1;
                    String kind = "";
                    if (opcode == 14 && ((next >>> 16) & 31) == register) {
                        computed = (high + (short)(next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/addi";
                    }
                    else if (opcode == 24 && ((next >>> 21) & 31) == register) {
                        computed = (high | (next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/ori";
                    }
                    if (computed == wanted) {
                        result.add(hex(value) + "->" + hex(site) + "(" + kind + "," +
                            owner(address(value)) + ")");
                    }
                }
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

    private void addOwner(Set<Function> functions, Address value) {
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(value);
        if (owner != null) functions.add(owner);
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

    private void writeRawInstructions(BufferedWriter output, long start, long end)
            throws Exception {
        output.write("RAW_INSTRUCTIONS " + hex(start) + ".." + hex(end) + "\n");
        for (long value = start; value < end; value += 4) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write(hex(value) + " " +
                (instruction == null ? "<none>" : instruction.toString()) + " refs=" +
                String.join(";", referencesTo(cursor)) + "\n");
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException(
            "usage: ApfPregameAnimsOwnerTrace.java OUTPUT_FILE");
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) throw new IllegalStateException("unexpected APF MD5 " + md5);

        Set<Function> focused = new LinkedHashSet<>();
        focused.add(ensureFunction(0x84692530L)); // instantiated MRKS registry-node constructor
        focused.add(ensureFunction(0x84692470L)); // MRKS pointer relocator

        File outputFile = new File(args[0]);
        File parent = outputFile.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(outputFile))) {
            output.write("APF_PREGAMEANIMS_OWNER_TRACE_V1\n");
            output.write("PROGRAM_MD5 " + md5 + "\n");
            output.write("READ_ONLY true\n");
            output.write("BOUNDARY static absence is not runtime non-execution proof\n\n");

            for (String literal : LITERALS) {
                List<Address> hits = findBytes(utf16be(literal), false);
                output.write("LITERAL " + literal + " encoding=UTF16BE hits=" + hits.size());
                for (Address hit : hits) {
                    output.write(" " + hex(hit.getUnsignedOffset()) + "[" +
                        String.join(";", referencesTo(hit)) + "]");
                    addOwner(focused, hit);
                }
                output.write("\n");
            }
            output.write("\n");

            for (long[] row : HASHES) {
                long value = row[0];
                String label = HASH_LABELS[(int)row[1]];
                List<Address> hits = wordHits(value);
                output.write("HASH " + label + " value=" + hex(value) + " aligned_hits=" +
                    hits.size() + " materializations=" +
                    String.join(";", materializations(value)) + "\n");
                for (Address hit : hits) {
                    output.write("  HIT " + hex(hit.getUnsignedOffset()) + " block=" +
                        currentProgram.getMemory().getBlock(hit).getName() + " owner=" +
                        owner(hit) + " refs=" + String.join(";", referencesTo(hit)) + "\n");
                    if (row[1] <= 4) addOwner(focused, hit);
                }
            }
            output.write("\n");

            writeWindow(output, 0x82006360L, 0x820063C0L);
            writeWindow(output, 0x84D22EA0L, 0x84D22EC0L);
            writeRawInstructions(output, 0x84692470L, 0x846926B0L);

            // Follow executable callback pointers in the static MRKS table.
            Memory memory = currentProgram.getMemory();
            for (long slot = 0x82006360L; slot < 0x820063C0L; slot += 4) {
                long raw = Integer.toUnsignedLong(memory.getInt(address(slot)));
                MemoryBlock block = memory.getBlock(address(raw));
                if (block != null && block.isExecute()) focused.add(ensureFunction(raw));
            }

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
        println("APF pregameanims ownership trace written to " + outputFile);
    }
}
