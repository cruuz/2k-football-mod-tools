// Read-only evidence trace for APF 2K8 retained awards and tournament data.
// @category VisualConcepts.Menu

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfCutContentFollowupTrace extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[] TARGETS = {
        0x820FABB0L, // LAYT / tournament-tree hash table.
        0x820FABC8L, // playoff_setup CRC32 field in that table.
        0x84614D6CL, // UTF-16BE "tourney_game %d".
        0x8200FB38L, // OnlineLiveDraft menu descriptor candidate.
        0x8200FB60L, // live_draft resource descriptor candidate.
        0x8451618CL, // UTF-16BE "Live Draft".
        0x845161A4L, // UTF-16BE "OnlineLiveDraft_Menu".
        0x845161D0L  // UTF-16BE "live_draft".
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String addr(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String owner(Address value) {
        Function function = currentProgram.getFunctionManager().getFunctionContaining(value);
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private String referencesTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            values.add(addr(reference.getFromAddress()) + "(" + owner(reference.getFromAddress()) +
                "," + reference.getReferenceType() + ")");
        }
        Collections.sort(values);
        return String.join(";", values);
    }

    private List<String> fullwordOccurrences(long target) throws Exception {
        byte[] needle = {
            (byte)(target >>> 24), (byte)(target >>> 16),
            (byte)(target >>> 8), (byte)target
        };
        List<String> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                if ((hit.getUnsignedOffset() & 3L) == 0) {
                    result.add(addr(hit) + "(" + block.getName() + "," + owner(hit) + ")");
                }
                cursor = hit.add(1);
            }
        }
        Collections.sort(result);
        return result;
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
                for (int distance = 1; distance <= 12; distance++) {
                    long nextAddress = value + distance * 4L;
                    if (nextAddress + 3 > last) break;
                    long next = Integer.toUnsignedLong(memory.getInt(address(nextAddress)));
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
                        result.add(hex(value) + "->" + hex(nextAddress) + "(" + kind + "," +
                            owner(address(value)) + ")");
                    }
                }
            }
        }
        Collections.sort(result);
        return result;
    }

    private void writeRange(BufferedWriter output, long first, long afterLast) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast) + "\n");
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            output.write(hex(value) + " raw=" +
                hex(Integer.toUnsignedLong(currentProgram.getMemory().getInt(cursor))) +
                " instruction=" + (instruction == null ? "<none>" : instruction.toString()) +
                " owner=" + owner(cursor) + " refs=" + referencesTo(cursor) + "\n");
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfCutContentFollowupTrace.java OUTPUT_FILE");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) throw new IllegalStateException("unexpected APF MD5 " + md5);

        File outputFile = new File(args[0]);
        File parent = outputFile.getParentFile();
        if (parent != null) parent.mkdirs();
        try (BufferedWriter output = new BufferedWriter(new FileWriter(outputFile))) {
            output.write("APF_CUT_CONTENT_FOLLOWUP_TRACE_V1\n");
            output.write("PROGRAM_MD5 " + md5 + "\n");
            output.write("READ_ONLY true\n");
            for (long target : TARGETS) {
                Address at = address(target);
                MemoryBlock block = currentProgram.getMemory().getBlock(at);
                output.write("TARGET " + hex(target) + " section=" +
                    (block == null ? "none" : block.getName()) + " owner=" + owner(at) +
                    " refs=" + referencesTo(at) +
                    " fullwords=" + String.join(";", fullwordOccurrences(target)) +
                    " materializations=" + String.join(";", materializations(target)) + "\n");
            }
            writeRange(output, 0x84A718E0L, 0x84A71B00L);
        }
        println("APF cut-content follow-up trace written to " + outputFile.getAbsolutePath());
    }
}
