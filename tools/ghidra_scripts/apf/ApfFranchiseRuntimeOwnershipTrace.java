// Trace APF 2K8 retail-season and retained franchise runtime ownership.
// @category VisualConcepts.Menu

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
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
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ApfFranchiseRuntimeOwnershipTrace extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[] TARGETS = {
        // Retained old-menu state descriptors.
        0x820E0B80L, 0x820E0BC8L, 0x820E0C10L,
        0x820E0E50L, 0x820E1020L, 0x820E1068L, 0x820E1908L, 0x820E4B04L,
        // Retail Season descriptors and Trophy Room descriptors.
        0x820F3AC0L, 0x820F3FC0L, 0x820F4094L, 0x820F4098L,
        0x820F42C0L, 0x820F4308L,
        0x820F8D78L, 0x820F8ED0L,
        0x820FAB68L,
        // Function roots/callbacks whose ownership distinguishes live and orphan paths.
        0x849DF2F0L, 0x84A1FCB0L, 0x84A1FD00L, 0x84A20020L,
        0x84A54A00L, 0x84A54BB0L, 0x84A55B50L,
        0x84AEE800L, 0x84AEE9E8L, 0x84AEEA90L,
        0x84AEF100L, 0x84AEF1C0L, 0x84AEFB40L,
        0x84B00948L,
        // Exact static row pointers linking retail Main/Season to old-menu code.
        0x84E55F10L, 0x84E57408L,
        // Archive/source/name strings.
        0x845FD740L, 0x845FD7E8L, 0x845FD930L,
        0x8460AF2CL, 0x8460AF48L, 0x84613288L, 0x846132A8L,
        0x84626428L, 0x84626450L, 0x8462651CL, 0x84626550L,
        // APF-adapted and unambiguously old NFL/ESPN retail strings.
        0x845F3268L, 0x845F3400L, 0x8461F500L, 0x8461F730L,
        // Primary English localization IDs retained in the retail resource.
        0x158A4351L, 0x1E9CD26FL, 0x3D5BA92BL, 0x40D827D3L,
        0x434CF7BDL, 0x517CB475L, 0x532064B3L, 0x547AABF1L,
        0x626D3137L, 0xADBCC0D3L, 0xB119D091L, 0xBB51037BL,
        0xCC699B7FL
    };

    private static final long[] FOCUS_SITES = {
        0x849DF2F0L, 0x849DF3B0L,
        0x84A1AC30L, 0x84A1ACB8L,
        0x84A1D438L, 0x84A1D544L, 0x84A1FB80L, 0x84A1FC20L,
        0x84A1FD00L, 0x84A1FD6CL,
        0x84A20408L, 0x84A20454L, 0x84A20A70L, 0x84A20AB4L, 0x84A21CC8L,
        0x84A54A00L, 0x84A59A10L, 0x84A6A980L,
        0x84A54BB0L, 0x84A55B50L,
        0x84ADE280L, 0x84AEE800L, 0x84AEE9E8L, 0x84AEEA90L,
        0x84AEF100L, 0x84AEF1C0L, 0x84AEFB40L,
        0x84AEF3F8L, 0x84AEF4B8L, 0x84AEF5F8L,
        0x84B007E0L, 0x84B00948L
    };

    private static final long[][] REBUILDS = {
        {0x849DF2F0L, 0x849DF2F8L, 0x849DF3E0L},
        {0x84A1D438L, 0x84A1D440L, 0x84A1D5B4L},
        {0x84A1FB80L, 0x84A1FB88L, 0x84A1FC5CL},
        {0x84A1FD00L, 0x84A1FD08L, 0x84A1FDCCL},
        {0x84A20A70L, 0x84A20A78L, 0x84A20B98L},
        {0x84A55B50L, 0x84A55B58L, 0x84A55EACL},
        {0x84ADE280L, 0x84ADE288L, 0x84ADE3BCL},
        {0x84AEEA90L, 0x84AEEAA0L, 0x84AEEC50L},
        {0x84AEF1C0L, 0x84AEF1C8L, 0x84AEF340L},
        {0x84AEF5F8L, 0x84AEF600L, 0x84AEF6E8L},
        {0x84B00948L, 0x84B00950L, 0x84B01574L}
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

    private String functionName(Function function) {
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private String referencesTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
            values.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
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
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
                    result.add(addr(hit) + "(" + block.getName() + "," + functionName(owner) + ")");
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
                int baseRegister = (int)((raw >>> 21) & 31);
                long high = ((long)(short)(raw & 0xffffL) << 16) & 0xffffffffL;
                for (int distance = 1; distance <= 12; distance++) {
                    long site = value + distance * 4L;
                    if (site + 3 > last) break;
                    long next = Integer.toUnsignedLong(memory.getInt(address(site)));
                    int opcode = (int)(next >>> 26);
                    long computed = -1;
                    String kind = "";
                    if (opcode == 14 && ((next >>> 16) & 31) == baseRegister) {
                        computed = (high + (short)(next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/addi";
                    }
                    else if (opcode == 24 && ((next >>> 21) & 31) == baseRegister) {
                        computed = (high | (next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/ori";
                    }
                    if (computed == wanted) {
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(address(value));
                        result.add(hex(value) + "->" + hex(site) + "(" + kind + "," +
                            functionName(owner) + ")");
                    }
                }
            }
        }
        Collections.sort(result);
        return result;
    }

    private void writeRawRange(BufferedWriter output, long first, long afterLast) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast) + "\n");
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(cursor);
            output.write(hex(value) + " raw=" + hex(Integer.toUnsignedLong(
                currentProgram.getMemory().getInt(cursor))) + " instruction=" +
                (instruction == null ? "<none>" : instruction.toString()) + " owner=" +
                functionName(owner) + " refs=" + referencesTo(cursor) + "\n");
        }
    }

    private void writePseudo(BufferedWriter output, DecompInterface decompiler, Function function)
            throws Exception {
        output.write("/* " + functionName(function) + " body=" +
            addr(function.getBody().getMinAddress()) + ".." +
            addr(function.getBody().getMaxAddress()) + " */\n");
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
            String text = result.getDecompiledFunction().getC();
            output.write(text);
            if (text.contains("Could not recover jumptable") ||
                    text.contains("Bad instruction") || text.contains("halt_baddata")) {
                output.write("// PORTME: Ghidra did not structurally recover all control flow for " +
                    addr(function.getEntryPoint()) +
                    "; use the frozen raw range as authoritative.\n");
            }
        }
        else {
            output.write("// PORTME: could not decompile function at " +
                addr(function.getEntryPoint()) + "; " + result.getErrorMessage() + "\n");
        }
        output.write("\n");
    }

    private void removeFunctionsIn(long first, long afterLast) throws Exception {
        Address start = address(first);
        Address end = address(afterLast - 1);
        List<Address> entries = new ArrayList<>();
        Function containing = currentProgram.getFunctionManager().getFunctionContaining(start);
        if (containing != null) entries.add(containing.getEntryPoint());
        FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(start, true);
        while (iterator.hasNext()) {
            Function function = iterator.next();
            if (function.getEntryPoint().compareTo(end) > 0) break;
            if (!entries.contains(function.getEntryPoint())) entries.add(function.getEntryPoint());
        }
        for (Address entry : entries) currentProgram.getFunctionManager().removeFunction(entry);
    }

    private Function rebuild(long trueEntry, long bodyEntry, long afterLast, int index)
            throws Exception {
        removeFunctionsIn(trueEntry, afterLast);
        Address first = address(trueEntry);
        Address last = address(afterLast - 1);
        clearListing(first, last);
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            disassemble(cursor);
        }
        Address body = address(bodyEntry);
        return currentProgram.getListing().createFunction(
            "APF_FranchiseOwnership_Rebuilt_" + index, body,
            new AddressSet(body, last), SourceType.ANALYSIS);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfFranchiseRuntimeOwnershipTrace.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) throw new IllegalStateException("unexpected APF MD5 " + md5);
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        for (long helper : new long[] {0x84BD6DC0L, 0x84BD6DCCL, 0x84BD6DD0L,
                0x84BD6DD4L, 0x84BD6DD8L, 0x84BD6DDCL, 0x84BD6DE0L,
                0x84BD6DE4L, 0x84BD6DE8L, 0x84BD6DECL, 0x84BD6E30L,
                0x84BD6E3CL, 0x84BDA5E0L, 0x84BDA5ECL, 0x84BDA5F0L,
                0x84BDA5F4L, 0x84BDA5F8L, 0x84BDA5FCL, 0x84BDA600L}) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(helper));
            if (function != null) function.setNoReturn(false);
        }

        Set<Function> functions = new LinkedHashSet<>();
        List<Function> rebuilt = new ArrayList<>();
        for (int index = 0; index < REBUILDS.length; index++) {
            Function function = rebuild(REBUILDS[index][0], REBUILDS[index][1],
                REBUILDS[index][2], index);
            rebuilt.add(function);
            functions.add(function);
        }
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(
                new File(directory, "apf_franchise_runtime_ownership_trace.txt")))) {
            trace.write("APF franchise/season runtime ownership read-only trace\n");
            trace.write("Program MD5: " + md5 + "\n");
            trace.write("Transient function rebuilds are discarded by -readOnly.\n\n");
            trace.write("REBUILT_BOUNDARIES\n");
            for (int index = 0; index < REBUILDS.length; index++) {
                trace.write("true_entry=" + hex(REBUILDS[index][0]) +
                    " body_entry=" + hex(REBUILDS[index][1]) +
                    " end_exclusive=" + hex(REBUILDS[index][2]) +
                    " transient=" + functionName(rebuilt.get(index)) + "\n");
            }
            trace.write("\nTARGETS\n");
            for (long target : TARGETS) {
                Address value = address(target);
                MemoryBlock block = currentProgram.getMemory().getBlock(value);
                trace.write(hex(target) + " section=" + (block == null ? "UNMAPPED" : block.getName()) +
                    " function_at=" + functionName(currentProgram.getFunctionManager().getFunctionAt(value)) +
                    " owner=" + functionName(currentProgram.getFunctionManager().getFunctionContaining(value)) +
                    " refs=" + referencesTo(value) + " fullwords=" +
                    String.join(";", fullwordOccurrences(target)) + " materializations=" +
                    String.join(";", materializations(target)) + "\n");
            }
            trace.write("\nFOCUS_OWNERS\n");
            for (long site : FOCUS_SITES) {
                Function function = currentProgram.getFunctionManager().getFunctionContaining(address(site));
                trace.write(hex(site) + " owner=" + functionName(function) + "\n");
                if (function != null) functions.add(function);
            }
            trace.write("\nRAW\n");
            writeRawRange(trace, 0x849DF2F0L, 0x849DF3E0L);
            writeRawRange(trace, 0x84A1AC30L, 0x84A1ACF8L);
            writeRawRange(trace, 0x84A1D438L, 0x84A1D5B4L);
            writeRawRange(trace, 0x84A1FB80L, 0x84A1FC5CL);
            writeRawRange(trace, 0x84A1FD00L, 0x84A1FDCCL);
            writeRawRange(trace, 0x84A203F0L, 0x84A20510L);
            writeRawRange(trace, 0x84A20A40L, 0x84A20B20L);
            writeRawRange(trace, 0x84A21C80L, 0x84A21D20L);
            writeRawRange(trace, 0x84A54A00L, 0x84A54AA0L);
            writeRawRange(trace, 0x84A54BB0L, 0x84A54C7CL);
            writeRawRange(trace, 0x84A55B50L, 0x84A55EACL);
            writeRawRange(trace, 0x84A6A980L, 0x84A6AA08L);
            writeRawRange(trace, 0x84ADE280L, 0x84ADE3BCL);
            writeRawRange(trace, 0x84AEE800L, 0x84AEE9E8L);
            writeRawRange(trace, 0x84AEEA90L, 0x84AEEC50L);
            writeRawRange(trace, 0x84AEF100L, 0x84AEF164L);
            writeRawRange(trace, 0x84AEF1C0L, 0x84AEF340L);
            writeRawRange(trace, 0x84AEF3F8L, 0x84AEF530L);
            writeRawRange(trace, 0x84AEF5F8L, 0x84AEF6E8L);
            writeRawRange(trace, 0x84AEFB40L, 0x84AEFBE0L);
            writeRawRange(trace, 0x84B007E0L, 0x84B008D8L);
            writeRawRange(trace, 0x84B00948L, 0x84B00AC0L);
        }

        List<Function> sorted = new ArrayList<>(functions);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException("decompiler open failed");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory, "apf_franchise_runtime_ownership_pseudo_c.c")))) {
            pseudo.write("/* APF franchise/season runtime ownership focused pseudo-C. */\n\n");
            for (Function function : sorted) writePseudo(pseudo, decompiler, function);
        }
        finally {
            decompiler.dispose();
        }
        println("APF_FRANCHISE_RUNTIME_OWNERSHIP_TRACE_COMPLETE functions=" + sorted.size());
    }
}
