// Emit focused static evidence for APF 2K8's DRCT resource lookup sites.
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
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfDirectorTrace extends GhidraScript {
    private static final long DRCT_CRC32 = 0xED586383L;
    private static final long DIRECTOR_CRC32 = 0x1E90D3F0L;
    private static final long DRAM_CRC32 = 0xBB05A9C1L;
    private static final long DIRECTOR_REGISTRY_START = 0x84D1B7D0L;
    private static final long DIRECTOR_REGISTRY_END = 0x84D1B870L;
    private static final long[] FOCUSED_FUNCTIONS = {
        0x8466AF70L, // dir_ingame.iff registration/load
        0x8466AFD8L, // matching unload
        0x8466B9D0L, // constructor touching the DRCT registry node
        0x8468CFC0L, // resource release-like consumer
        0x8468DA70L, // resource registration/load consumer
        0x84690FA0L, // owner that invokes the director load/unload callbacks
        0x849D8CE8L, // adjacent tutorial director load site
        0x849D8DA8L, // dir_tutorial.iff load site
        0x84AECCD0L  // dir_wrapup.iff path consumer
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
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private Set<Address> findWord(Memory memory, long value) throws Exception {
        Set<Address> result = new LinkedHashSet<>();
        byte[] pattern = {
            (byte)(value >>> 24), (byte)(value >>> 16),
            (byte)(value >>> 8), (byte)value
        };
        for (MemoryBlock block : memory.getBlocks()) {
            Address cursor = block.getStart();
            while (cursor != null && cursor.compareTo(block.getEnd()) <= 0) {
                Address found = memory.findBytes(
                    cursor, block.getEnd(), pattern, null, true, monitor);
                if (found == null) break;
                result.add(found);
                if (found.equals(block.getEnd())) break;
                cursor = found.add(1);
            }
        }
        return result;
    }

    private boolean hasHalfword(Instruction instruction, int wanted) {
        for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
            for (Object object : instruction.getOpObjects(operand)) {
                if (object instanceof Scalar) {
                    long value = ((Scalar)object).getUnsignedValue();
                    if ((value & 0xffffL) == wanted) return true;
                }
            }
        }
        return false;
    }

    private void writeWindow(BufferedWriter stream, Instruction center) throws Exception {
        Address start = center.getAddress();
        for (int i = 0; i < 5; i++) {
            Instruction previous = currentProgram.getListing().getInstructionBefore(start);
            if (previous == null) break;
            start = previous.getAddress();
        }
        Address cursor = start;
        for (int i = 0; i < 13; i++) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) break;
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(cursor);
            stream.write((cursor.equals(center.getAddress()) ? "=> " : "   ") +
                hex(cursor.getUnsignedOffset()) + " " + instruction + " owner=" +
                functionName(owner) + "\n");
            cursor = instruction.getMaxAddress().add(1);
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfDirectorTrace.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(md5) &&
            !"c6f5639ac4c428682db0362947a223d8".equalsIgnoreCase(md5) &&
            !"5370d49a9542d60c0345391e4e4aa656".equalsIgnoreCase(md5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + md5);
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }

        Memory memory = currentProgram.getMemory();
        Set<Function> owners = new LinkedHashSet<>();
        List<Instruction> halfwordHits = new ArrayList<>();
        InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            if (hasHalfword(instruction, 0xED58) ||
                hasHalfword(instruction, 0x6383)) {
                halfwordHits.add(instruction);
            }
        }
        for (long value : FOCUSED_FUNCTIONS) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(
                address(value));
            if (function != null) owners.add(function);
        }

        File traceFile = new File(output, "director_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 DRCT focused static trace\n");
            trace.write("Program MD5: " + md5 + "\n");
            trace.write("Program language: " + currentProgram.getLanguageID() + "\n");
            trace.write("CRC32('DRCT')=" + hex(DRCT_CRC32) + "\n");
            trace.write("CRC32('director')=" + hex(DIRECTOR_CRC32) + "\n");
            trace.write("CRC32('DRAM')=" + hex(DRAM_CRC32) + "\n");
            trace.write("Constraint: scalar hits are evidence locations, not field names.\n\n");

            for (long value : new long[] {DRCT_CRC32, DIRECTOR_CRC32, DRAM_CRC32}) {
                trace.write("WORD_MATCHES " + hex(value) + "\n");
                for (Address hit : findWord(memory, value)) {
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
                    if (owner != null) owners.add(owner);
                    trace.write(hex(hit.getUnsignedOffset()) + " block=" +
                        memory.getBlock(hit).getName() + " owner=" + functionName(owner) +
                        " refs=" + String.join(";", referencesTo(hit)) + "\n");
                }
                trace.write("\n");
            }

            trace.write("DIRECTOR_REGISTRY_WINDOW\n");
            for (long value = DIRECTOR_REGISTRY_START;
                    value < DIRECTOR_REGISTRY_END; value += 4) {
                Address slot = address(value);
                long raw = Integer.toUnsignedLong(memory.getInt(slot));
                trace.write(hex(value) + " raw=" + hex(raw) + " refs=" +
                    String.join(";", referencesTo(slot)) + "\n");
            }
            trace.write("registry_base_refs=" +
                String.join(";", referencesTo(address(DIRECTOR_REGISTRY_START))) +
                "\n\n");

            trace.write("FOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED_FUNCTIONS) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                trace.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }
            trace.write("\n");

            trace.write("LOW_HALFWORD_COLLISIONS_NOT_DIRECT_DRCT_EVIDENCE\n");
            trace.write("The full 0xED586383 value occurs only in the registry word above; " +
                "these windows merely guard against mistaking a 16-bit collision for it.\n");
            for (Instruction hit : halfwordHits) {
                trace.write("\nHIT " + hex(hit.getAddress().getUnsignedOffset()) + " " + hit +
                    "\n");
                writeWindow(trace, hit);
            }
        }

        List<Function> sorted = new ArrayList<>(owners);
        sorted.sort((left, right) -> left.getEntryPoint().compareTo(right.getEntryPoint()));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "director_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF 2K8 DRCT constant owners; unknown fields stay unnamed. */\n\n");
            for (Function function : sorted) {
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 30 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint().getUnsignedOffset()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_DIRECTOR_TRACE_COMPLETE halfword_hits=" + halfwordHits.size() +
            " owner_functions=" + sorted.size());
    }
}
