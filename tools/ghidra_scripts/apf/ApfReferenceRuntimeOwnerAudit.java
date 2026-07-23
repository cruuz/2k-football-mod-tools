// Read-only ownership/reachability audit for APF 2K8's retained REFR support.
// @category Xbox360.APF2K8

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

public class ApfReferenceRuntimeOwnerAudit extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[] TARGETS = {
        0x84AB0D58L, // REFR pointer relocation worker
        0x84AB0E98L, // inverse pointer serialization worker
        0x84AB0FA8L, // package/resource lookup and global assignment
        0x84AB1028L, // group count accessor
        0x84AB1040L, // group table accessor
        0x84AB1058L, // bounded record accessor
        0x84AB1090L, // REFR registry-node constructor
        0x84AB10C0L, // REFR DRAM load callback
        0x84AB1110L, // registry link
        0x84AB1148L, // registry unlink
        0x84AB1178L, // node destructor
        0x84AB11A8L, // node deleting destructor
        0x84AB1210L, // duplicate REFR registry-node constructor
        0x84AB1240L, // duplicate node destructor
        0x84AB1270L, // virtual fail-fast thunk
        0x84AB12E0L, // runtime helper
        0x84AB1320L, // runtime helper
        0x84690C68L, // small subsystem init sequence containing registry link
        0x84690CB0L, // small subsystem teardown sequence containing registry unlink
        0x84690FA0L, // full subsystem teardown sequence
        0x84691650L, // full subsystem initialization sequence
        0x84691C68L, // caller of full initialization/teardown
        0x84B8B1D0L, // CRT main wrapper
        0x84BE9D10L, // analyzed XEX entry body (true body after save-GPR thunk)
        0x84BE9E9CL, // XEX entry call site to CRT main
        0x84B8B1E0L, // CRT main call site to game main loop
        0x84691CC0L, // main-loop call site to full bootstrap
        0x8469170CL, // full bootstrap's direct call to the REFR registry link
        0x84691114L, // full teardown's direct call to the REFR registry unlink
        0x84691CDCL, // main loop's direct call to full teardown
        0x820FEAFCL, // REFR static descriptor/type hash
        0x820FEB00L, // REFR static callback/vtable descriptor
        0x84EAB870L, // instantiated REFR registry node
        0x84D07540L, // static initializer materializing the runtime node
        0x85234EB0L, // loaded REFR body global
        0x15578F45L, // CRC32("REFR")
        0xBB05A9C1L, // CRC32("DRAM")
        0xF0D95EFAL, // CRC32("REFERENCE_DATA")
        0xBE047DD2L  // CRC32("REFERENCE.IFF")
    };

    private static final long[] FOCUS_FUNCTIONS = {
        0x84AB0D58L, 0x84AB0E98L, 0x84AB0FA8L, 0x84AB1028L,
        0x84AB1040L, 0x84AB1058L, 0x84AB1090L, 0x84AB10C0L,
        0x84AB1110L, 0x84AB1148L, 0x84AB1178L, 0x84AB11A8L,
        0x84AB1210L, 0x84AB1240L,
        0x84AB1270L, 0x84AB12E0L, 0x84AB1320L,
        0x84690C68L, 0x84690CB0L, 0x84690FA0L, 0x84691650L,
        0x84691C68L, 0x84B8B1D0L
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
        Collections.sort(values);
        return values;
    }

    private List<Address> findBytes(byte[] needle, boolean aligned) throws Exception {
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

    private List<String> fullwordOccurrences(long target) throws Exception {
        byte[] needle = {
            (byte)(target >>> 24), (byte)(target >>> 16),
            (byte)(target >>> 8), (byte)target
        };
        List<String> result = new ArrayList<>();
        for (Address hit : findBytes(needle, true)) {
            MemoryBlock block = currentProgram.getMemory().getBlock(hit);
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
            result.add(hex(hit.getUnsignedOffset()) + "(" +
                (block == null ? "UNMAPPED" : block.getName()) + "," +
                functionName(owner) + ")");
        }
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
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                            address(value));
                        result.add(hex(value) + "->" + hex(site) + "(" + kind + "," +
                            functionName(owner) + ")");
                    }
                }
            }
        }
        Collections.sort(result);
        return result;
    }

    private List<String> dFormUses(long target) throws Exception {
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
                for (int distance = 1; distance <= 4; distance++) {
                    long site = value + 4L * distance;
                    if (site + 3 > last) break;
                    long next = Integer.toUnsignedLong(memory.getInt(address(site)));
                    int opcode = (int)(next >>> 26);
                    int baseRegister = (int)((next >>> 16) & 31);
                    // Integer/floating D-form loads and stores. Exclude update forms,
                    // which alter the base register and are irrelevant at these sites.
                    if (opcode >= 32 && opcode <= 55 && (opcode & 1) == 0 &&
                            baseRegister == register) {
                        long computed = (high + (short)(next & 0xffffL)) & 0xffffffffL;
                        if (computed == wanted) {
                            Function owner = currentProgram.getFunctionManager()
                                .getFunctionContaining(address(value));
                            result.add(hex(value) + "->" + hex(site) + "(opcode=" +
                                opcode + "," + functionName(owner) + ")");
                        }
                    }
                }
            }
        }
        Collections.sort(result);
        return result;
    }

    private void writeFunction(BufferedWriter output, Function function) throws Exception {
        output.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody() + " incoming=" +
            String.join(";", referencesTo(function.getEntryPoint())) + "\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " +
                instruction + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
        output.write("\n");
    }

    private void writeWindow(BufferedWriter output, long start, long end) throws Exception {
        Memory memory = currentProgram.getMemory();
        output.write("WINDOW " + hex(start) + ".." + hex(end) + "\n");
        for (long value = start; value < end; value += 4) {
            Address cursor = address(value);
            MemoryBlock block = memory.getBlock(cursor);
            if (block == null || !block.isInitialized()) {
                output.write(hex(value) + " UNMAPPED\n");
                continue;
            }
            ghidra.program.model.listing.Instruction instruction =
                currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null && block.isExecute()) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write(hex(value) + " raw=" +
                hex(Integer.toUnsignedLong(memory.getInt(cursor))) + " refs=" +
                String.join(";", referencesTo(cursor)) + " owner=" +
                functionName(currentProgram.getFunctionManager().getFunctionContaining(cursor)) +
                " instruction=" + (instruction == null ? "<none>" : instruction.toString()) +
                "\n");
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException(
            "usage: ApfReferenceRuntimeOwnerAudit.java OUTPUT_DIRECTORY");
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) throw new IllegalStateException("unexpected APF MD5 " + md5);
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> functions = new LinkedHashSet<>();
        for (long value : FOCUS_FUNCTIONS) functions.add(ensureFunction(value));
        // The saved project truncates the 0x84691650 bootstrap immediately after
        // its save-GPR thunk. Materialize this narrow fixed-width window so the
        // direct 0x8469170C -> 0x84AB1110 edge is visible without rebuilding the
        // several-kilobyte function boundary.
        for (long value = 0x846916E0L; value < 0x84691730L; value += 4) {
            if (currentProgram.getListing().getInstructionAt(address(value)) == null) {
                disassemble(address(value));
            }
        }

        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "apf_reference_runtime_owner_trace.txt")))) {
            output.write("APF 2K8 reference.iff runtime ownership/reachability audit\n");
            output.write("Program MD5: " + md5 + "\n");
            output.write("Constraint: read-only static evidence; registration is not display reachability.\n\n");
            output.write("TARGETS\n");
            for (long target : TARGETS) {
                Address value = address(target);
                MemoryBlock block = currentProgram.getMemory().getBlock(value);
                output.write(hex(target) + " section=" +
                    (block == null ? "UNMAPPED" : block.getName()) + " function_at=" +
                    functionName(currentProgram.getFunctionManager().getFunctionAt(value)) +
                    " owner=" + functionName(
                        currentProgram.getFunctionManager().getFunctionContaining(value)) +
                    " refs=" + String.join(";", referencesTo(value)) +
                    " fullwords=" + String.join(";", fullwordOccurrences(target)) +
                    " materializations=" + String.join(";", materializations(target)) +
                    " dform_uses=" + String.join(";", dFormUses(target)) + "\n");
            }

            output.write("\nTEXT_OCCURRENCES\n");
            for (String text : new String[] {"reference.iff", "reference_data",
                    "open_book", "closed_book", "REFERENCE", "REFR"}) {
                for (String encoding : new String[] {"ASCII", "UTF16BE"}) {
                    byte[] needle = encoding.equals("ASCII") ?
                        text.getBytes(StandardCharsets.US_ASCII) :
                        text.getBytes(StandardCharsets.UTF_16BE);
                    List<String> hits = new ArrayList<>();
                    for (Address hit : findBytes(needle, false)) {
                        MemoryBlock block = currentProgram.getMemory().getBlock(hit);
                        hits.add(hex(hit.getUnsignedOffset()) + "(" +
                            (block == null ? "UNMAPPED" : block.getName()) + "," +
                            functionName(currentProgram.getFunctionManager().getFunctionContaining(hit)) +
                            ")");
                    }
                    output.write(text + " " + encoding + "=" + String.join(";", hits) + "\n");
                }
            }

            output.write("\nDATA_WINDOWS\n");
            writeWindow(output, 0x820FEAE0L, 0x820FEB40L);
            writeWindow(output, 0x846916E0L, 0x84691730L);
            writeWindow(output, 0x84B8B1D0L, 0x84B8B218L);
            writeWindow(output, 0x84BE9E90L, 0x84BE9EA8L);
            writeWindow(output, 0x84D07540L, 0x84D07580L);
            writeWindow(output, 0x84EAB850L, 0x84EAB8D0L);
            writeWindow(output, 0x85234E80L, 0x85234ED0L);

            output.write("FUNCTIONS\n");
            for (Function function : functions) writeFunction(output, function);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException(
            "decompiler open failed");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "apf_reference_runtime_owner_pseudo_c.c")))) {
            for (Function function : functions) {
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
        println("APF_REFERENCE_RUNTIME_OWNER_AUDIT_COMPLETE functions=" + functions.size());
    }
}
