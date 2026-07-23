// Emit exact read-only evidence for APF 2K8 cold boot and frontend backdrop ownership.
// @category VisualConcepts.Menu

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.security.MessageDigest;
import java.util.ArrayList;
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

public class ApfFrontendBootBackdropV5 extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    // End values are exclusive and are proven by PDATA length metadata or the
    // next aligned entry.  +8 bodies skip the compiler's out-of-line save helper.
    private static final long[][] REBUILDS = {
        {0x84BE9D08L, 0x84BE9D10L, 0x84BE9EC8L}, // XEX title entry.
        {0x846913E0L, 0x846913E8L, 0x8469154CL}, // per-frame main-loop iteration.
        {0x84691650L, 0x84691658L, 0x84691C68L}, // game/frontend bootstrap.
        {0x846E0338L, 0x846E0340L, 0x846E0468L}, // TitlePage update callback.
        {0x846F9360L, 0x846F9368L, 0x846F9480L}, // state-runtime registration.
        {0x84A59E68L, 0x84A59E70L, 0x84A5A4C4L}  // StartupMenu callback.
    };

    private static final String[] REBUILD_NAMES = {
        "APF_XexEntry_Body",
        "APF_MainLoopIteration_Body",
        "APF_FrontendBootstrap_Body",
        "APF_TitlePageUpdate_Body",
        "APF_StateRuntimeRegister_Body",
        "APF_StartupMenuCallback_Body"
    };

    private static final long[] SAVED_FOCUS = {
        0x84B8B1D0L, 0x84B8AF98L, 0x84691C68L,
        0x846E0468L, 0x846E0528L,
        0x846F2590L, 0x846F8778L, 0x846F89B0L, 0x846F89B8L,
        0x846F8A60L, 0x846F9090L
    };

    private static final long[] STATIC_TARGETS = {
        0x82015330L, 0x82015304L, 0x82015298L, 0x820152BCL,
        0x820152D4L, 0x820152ECL,
        0x820F4940L, 0x820F4910L, 0x820F4898L, 0x820F48B0L,
        0x820F48C8L, 0x820F48E0L, 0x820F48F8L,
        0x820F4350L, 0x8451F2F0L, 0x8460D430L,
        0x8450232CL, 0x8467C8D0L, 0x8467C978L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String addr(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", value & 0xff));
        }
        return result.toString();
    }

    private List<String> referencesTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            values.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        values.sort(String::compareTo);
        return values;
    }

    private String rangeSha256(long first, long afterLast) throws Exception {
        int count = Math.toIntExact(afterLast - first);
        byte[] data = new byte[count];
        int read = currentProgram.getMemory().getBytes(address(first), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(first));
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder result = new StringBuilder();
        for (byte value : digest) result.append(String.format("%02x", value & 0xff));
        return result.toString();
    }

    private void removeFunctionsIn(long first, long afterLast) throws Exception {
        Address start = address(first);
        Address end = address(afterLast - 1);
        Set<Address> entries = new LinkedHashSet<>();
        Function containing = currentProgram.getFunctionManager().getFunctionContaining(start);
        if (containing != null) entries.add(containing.getEntryPoint());
        FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(start, true);
        while (iterator.hasNext()) {
            Function function = iterator.next();
            if (function.getEntryPoint().compareTo(end) > 0) break;
            entries.add(function.getEntryPoint());
        }
        for (Address entry : entries) {
            currentProgram.getFunctionManager().removeFunction(entry);
        }
    }

    private Function rebuildBody(long trueEntry, long bodyEntry, long afterLast, String name)
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
            name, body, new AddressSet(body, last), SourceType.ANALYSIS);
    }

    private Function ensureFunction(long value) throws Exception {
        Address entry = address(value);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function != null) return function;
        disassemble(entry);
        createFunction(entry, null);
        return currentProgram.getFunctionManager().getFunctionAt(entry);
    }

    private void writeTarget(BufferedWriter output, long value) throws Exception {
        Address target = address(value);
        Function at = currentProgram.getFunctionManager().getFunctionAt(target);
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(target);
        output.write(hex(value) + " section=" + section(target) +
            " function_at=" + functionName(at) + " owner=" + functionName(owner) +
            " refs=" + String.join(";", referencesTo(target)) + "\n");
    }

    private void writeRawRange(BufferedWriter output, long first, long afterLast)
            throws Exception {
        Memory memory = currentProgram.getMemory();
        output.write("RAW_RANGE " + hex(first) + ".." + hex(afterLast) +
            " bytes=" + (afterLast - first) + " sha256=" +
            rangeSha256(first, afterLast) + "\n");
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write(hex(value) + " raw=" + hex(raw) + " bytes=" +
                (instruction == null ? "" : bytes(instruction)) + " instruction=" +
                (instruction == null ? "<none>" : instruction.toString()) +
                " owner=" + functionName(
                    currentProgram.getFunctionManager().getFunctionContaining(cursor)) +
                " refs=" + String.join(";", referencesTo(cursor)) + "\n");
        }
    }

    private void writeStaticWords(BufferedWriter output, long first, int count)
            throws Exception {
        Memory memory = currentProgram.getMemory();
        output.write("STATIC_WORDS " + hex(first) + " count=" + count + "\n");
        for (int index = 0; index < count; index++) {
            long value = first + index * 4L;
            output.write(hex(value) + "=" +
                hex(Integer.toUnsignedLong(memory.getInt(address(value)))) + "\n");
        }
    }

    private String utf16(long first, int maximumUnits) throws Exception {
        Memory memory = currentProgram.getMemory();
        StringBuilder value = new StringBuilder();
        for (int index = 0; index < maximumUnits; index++) {
            int code = Short.toUnsignedInt(memory.getShort(address(first + index * 2L)));
            if (code == 0) break;
            value.append((char)code);
        }
        return value.toString();
    }

    private void writePseudo(BufferedWriter output, DecompInterface decompiler,
            Function function, String evidenceEntry) throws Exception {
        output.write("/* evidence_entry=" + evidenceEntry + " transient_function=" +
            functionName(function) + " body=" + addr(function.getBody().getMinAddress()) +
            ".." + addr(function.getBody().getMaxAddress()) + " */\n");
        DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
        if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
            output.write(result.getDecompiledFunction().getC());
        }
        else {
            String reason = result.isTimedOut() ? "timed out after 90 seconds" :
                result.getErrorMessage();
            output.write("// PORTME: could not decompile function at " + evidenceEntry +
                "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfFrontendBootBackdropV5.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + md5);
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        long[] sharedHelpers = {
            0x84BD6DC0L, 0x84BD6DCCL, 0x84BD6DD0L, 0x84BD6DD4L,
            0x84BD6DD8L, 0x84BD6DDCL, 0x84BD6DE0L, 0x84BD6DE4L,
            0x84BD6DE8L, 0x84BD6DECL, 0x84BD6E30L, 0x84BD6E3CL
        };
        for (long value : sharedHelpers) {
            Function helper = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (helper != null) helper.setNoReturn(false);
        }

        List<Function> rebuilt = new ArrayList<>();
        for (int index = 0; index < REBUILDS.length; index++) {
            rebuilt.add(rebuildBody(
                REBUILDS[index][0], REBUILDS[index][1], REBUILDS[index][2],
                REBUILD_NAMES[index]));
        }
        List<Function> saved = new ArrayList<>();
        for (long value : SAVED_FOCUS) {
            Function function = ensureFunction(value);
            if (function != null && !saved.contains(function)) saved.add(function);
        }

        File traceFile = new File(directory, "apf_frontend_boot_backdrop_v5_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 cold-boot/frontend-backdrop read-only v5 trace\n");
            trace.write("Program MD5: " + md5 + "\n");
            trace.write("All reconstructed functions are transient and discarded by -readOnly; " +
                "no project or executable byte is saved.\n\n");

            trace.write("REBUILT_BOUNDARIES\n");
            for (int index = 0; index < REBUILDS.length; index++) {
                trace.write("true_entry=" + hex(REBUILDS[index][0]) +
                    " body_entry=" + hex(REBUILDS[index][1]) +
                    " end_exclusive=" + hex(REBUILDS[index][2]) +
                    " transient=" + functionName(rebuilt.get(index)) + "\n");
            }

            trace.write("\nFOCUS_TARGETS\n");
            for (long value : SAVED_FOCUS) writeTarget(trace, value);
            for (long value : STATIC_TARGETS) writeTarget(trace, value);

            trace.write("\nSTATIC_DESCRIPTORS\n");
            writeStaticWords(trace, 0x82015330L, 18);
            writeStaticWords(trace, 0x82015304L, 10);
            writeStaticWords(trace, 0x82015298L, 28);
            writeStaticWords(trace, 0x820F4940L, 18);
            writeStaticWords(trace, 0x820F4910L, 10);
            writeStaticWords(trace, 0x820F4898L, 28);
            writeStaticWords(trace, 0x820F4350L, 18);
            trace.write("UTF16 " + hex(0x8451F2F0L) + "=" + utf16(0x8451F2F0L, 64) + "\n");
            trace.write("UTF16 " + hex(0x8460D430L) + "=" + utf16(0x8460D430L, 64) + "\n");
            trace.write("UTF16 " + hex(0x8450232CL) + "=" + utf16(0x8450232CL, 64) + "\n");

            trace.write("\nRAW_EVIDENCE\n");
            for (long[] range : REBUILDS) writeRawRange(trace, range[0], range[2]);
            writeRawRange(trace, 0x84B8B1D0L, 0x84B8B218L);
            writeRawRange(trace, 0x84691C68L, 0x84691D08L);
            writeRawRange(trace, 0x846E0468L, 0x846E0590L);
            writeRawRange(trace, 0x8467C8D0L, 0x8467CA10L);

            trace.write("\nPOST_REBUILD_TARGETS\n");
            for (long value : new long[] {
                0x84BE9D08L, 0x84BE9D10L, 0x846913E0L, 0x846913E8L,
                0x84691650L, 0x84691658L, 0x846E0338L, 0x846E0340L,
                0x846F9360L, 0x846F9368L, 0x84A59E68L, 0x84A59E70L,
                0x84691B74L, 0x846E0574L, 0x846F9458L, 0x846F9470L,
                0x84A5A4A8L
            }) writeTarget(trace, value);
        }

        rebuilt.sort(Comparator.comparing(Function::getEntryPoint));
        saved.sort(Comparator.comparing(Function::getEntryPoint));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "apf_frontend_boot_backdrop_v5_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF cold-boot/frontend pseudo-C. +8 transient bodies omit only " +
                "the out-of-line compiler save-helper call. */\n\n");
            for (Function function : rebuilt) {
                String evidence = "unknown";
                for (int index = 0; index < REBUILDS.length; index++) {
                    if (function.getEntryPoint().getUnsignedOffset() == REBUILDS[index][1]) {
                        evidence = hex(REBUILDS[index][0]);
                        break;
                    }
                }
                writePseudo(pseudo, decompiler, function, evidence);
            }
            for (Function function : saved) {
                writePseudo(pseudo, decompiler, function,
                    hex(function.getEntryPoint().getUnsignedOffset()));
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_FRONTEND_BOOT_BACKDROP_V5_TRACE_COMPLETE rebuilt=" + rebuilt.size() +
            " saved=" + saved.size());
    }
}
