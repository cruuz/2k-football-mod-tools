// Trace APF 2K8 frontend bundle/Main-menu construction ownership.
// @category VisualConcepts.Menu

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ApfFrontendMainOwnershipV6 extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[] FOCUS = {
        0x8467CA70L, 0x8467CB88L, 0x8468CFC0L, 0x8468DA70L,
        0x846DE230L, 0x846EFD38L, 0x846F0058L, 0x846F2590L,
        0x846F5518L,
        0x84A59758L, 0x84A59A10L, 0x84A59B10L, 0x84A69720L,
        0x846AF620L, 0x84A682C8L, 0x84A56900L
    };

    private static final long[][] REBUILDS = {
        {0x8467CA70L, 0x8467CA78L, 0x8467CB20L},
        {0x8467CB88L, 0x8467CB90L, 0x8467CC80L},
        {0x8468CFC0L, 0x8468CFC8L, 0x8468D038L},
        {0x8468D7D0L, 0x8468D7D8L, 0x8468D870L},
        {0x8468D870L, 0x8468D878L, 0x8468D910L},
        {0x8468DA70L, 0x8468DA78L, 0x8468DB64L},
        {0x846DE230L, 0x846DE238L, 0x846DE398L},
        {0x846F0058L, 0x846F0060L, 0x846F0190L},
        {0x846F5F48L, 0x846F5F50L, 0x846F6050L},
        {0x846F6060L, 0x846F6068L, 0x846F60E8L}
    };

    private static final String[] REBUILD_NAMES = {
        "APF_FrontendSyncRequest_Body",
        "APF_FrontendAsyncRequest_Body",
        "APF_ResourceRelease_Body",
        "APF_ResourceRequestDefault_Body",
        "APF_ResourceRequestOverride_Body",
        "APF_ResourceRequestDispatch_Body",
        "APF_ModeSpecificDescriptorRoute_Body",
        "APF_DescriptorDestroy_Body",
        "APF_MainRoutePolicyA_Body",
        "APF_MainRoutePolicyB_Body"
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
        values.sort(String::compareTo);
        return String.join(";", values);
    }

    private void writeTarget(BufferedWriter output, long value) throws Exception {
        Address target = address(value);
        MemoryBlock block = currentProgram.getMemory().getBlock(target);
        output.write(hex(value) + " section=" + (block == null ? "UNMAPPED" : block.getName()) +
            " function_at=" + functionName(currentProgram.getFunctionManager().getFunctionAt(target)) +
            " owner=" + functionName(currentProgram.getFunctionManager().getFunctionContaining(target)) +
            " refs=" + referencesTo(target) + "\n");
    }

    private void writeRange(BufferedWriter output, long first, long afterLast) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast) + "\n");
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write(hex(value) + " raw=" + hex(Integer.toUnsignedLong(
                currentProgram.getMemory().getInt(cursor))) + " instruction=" +
                (instruction == null ? "<none>" : instruction.toString()) + " owner=" +
                functionName(currentProgram.getFunctionManager().getFunctionContaining(cursor)) +
                " refs=" + referencesTo(cursor) + "\n");
        }
    }

    private void writeWords(BufferedWriter output, long first, int count) throws Exception {
        output.write("WORDS " + hex(first) + " count=" + count + "\n");
        for (int index = 0; index < count; index++) {
            long value = first + index * 4L;
            output.write(hex(value) + "=" + hex(Integer.toUnsignedLong(
                currentProgram.getMemory().getInt(address(value)))) + "\n");
        }
    }

    private String utf16(long first, int maximumUnits) throws Exception {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < maximumUnits; index++) {
            int code = Short.toUnsignedInt(currentProgram.getMemory().getShort(
                address(first + index * 2L)));
            if (code == 0) return result.toString();
            result.append((char)code);
        }
        throw new IllegalStateException("unterminated UTF-16BE at " + hex(first));
    }

    private void writePseudo(BufferedWriter output, DecompInterface decompiler, Function function)
            throws Exception {
        output.write("/* " + functionName(function) + " body=" + addr(function.getBody().getMinAddress()) +
            ".." + addr(function.getBody().getMaxAddress()) + " */\n");
        DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
        if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
            String text = result.getDecompiledFunction().getC();
            output.write(text);
            if (text.contains("Could not recover jumptable") ||
                    text.contains("Bad instruction") || text.contains("halt_baddata")) {
                output.write("// PORTME: Ghidra did not structurally recover all control flow for " +
                    addr(function.getEntryPoint()) + "; use the v6 raw instruction/jump-table " +
                    "range as authoritative before native translation.\n");
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

    private Function rebuild(long trueEntry, long bodyEntry, long afterLast, String name)
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

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfFrontendMainOwnershipV6.java OUTPUT_DIRECTORY");
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
                0x84BD6E3CL}) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(helper));
            if (function != null) function.setNoReturn(false);
        }

        List<Function> rebuilt = new ArrayList<>();
        List<Function> functions = new ArrayList<>();
        for (int index = 0; index < REBUILDS.length; index++) {
            Function function = rebuild(REBUILDS[index][0], REBUILDS[index][1],
                REBUILDS[index][2], REBUILD_NAMES[index]);
            rebuilt.add(function);
            functions.add(function);
        }
        for (long value : FOCUS) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function != null && !functions.contains(function)) functions.add(function);
        }
        functions.sort(Comparator.comparing(Function::getEntryPoint));

        try (BufferedWriter trace = new BufferedWriter(new FileWriter(
                new File(directory, "apf_frontend_main_ownership_v6_trace.txt")))) {
            trace.write("APF frontend_sync/Main ownership v6 read-only trace\nProgram MD5: " + md5 + "\n");
            trace.write("All function reconstruction is transient and discarded by -readOnly.\n\n");
            trace.write("REBUILT_BOUNDARIES\n");
            for (int index = 0; index < REBUILDS.length; index++) {
                trace.write("true_entry=" + hex(REBUILDS[index][0]) +
                    " body_entry=" + hex(REBUILDS[index][1]) +
                    " end_exclusive=" + hex(REBUILDS[index][2]) +
                    " transient=" + functionName(rebuilt.get(index)) + "\n");
            }
            trace.write("TARGETS\n");
            for (long value : FOCUS) writeTarget(trace, value);
            for (long value : new long[] {0x84691BB8L, 0x8450232CL, 0x84D21F68L,
                    0x820F4350L, 0x820F6D38L, 0x820F6D0CL, 0x84A56950L}) {
                writeTarget(trace, value);
            }
            trace.write("UTF16 " + hex(0x8450232CL) + "=" + utf16(0x8450232CL, 64) + "\n");
            trace.write("UTF16 " + hex(0x8460C04CL) + "=" + utf16(0x8460C04CL, 64) + "\n");
            trace.write("UTF16 " + hex(0x8460C088L) + "=" + utf16(0x8460C088L, 64) + "\n");
            trace.write("UTF16 " + hex(0x84612064L) + "=" + utf16(0x84612064L, 64) + "\n");
            trace.write("\nRAW\n");
            writeRange(trace, 0x84691B64L, 0x84691BDCL);
            writeRange(trace, 0x8467CA70L, 0x8467CB20L);
            writeRange(trace, 0x8468D7D0L, 0x8468D910L);
            writeRange(trace, 0x8468DA70L, 0x8468DB64L);
            writeRange(trace, 0x846DE230L, 0x846DE398L);
            writeRange(trace, 0x846EFD38L, 0x846EFE14L);
            writeRange(trace, 0x846F0058L, 0x846F0190L);
            writeRange(trace, 0x84A59758L, 0x84A59810L);
            writeRange(trace, 0x84A59A10L, 0x84A59A80L);
            writeRange(trace, 0x84A59B10L, 0x84A59BA4L);
            writeRange(trace, 0x84A5A49CL, 0x84A5A4C4L);
            writeRange(trace, 0x84A56900L, 0x84A569E8L);
            trace.write("\nSTATIC\n");
            writeWords(trace, 0x820F4350L, 18);
            writeWords(trace, 0x820F6D0CL, 29);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException("decompiler open failed");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory, "apf_frontend_main_ownership_v6_pseudo_c.c")))) {
            pseudo.write("/* APF frontend Main ownership v6 focused pseudo-C. */\n\n");
            for (Function function : functions) writePseudo(pseudo, decompiler, function);
        }
        finally {
            decompiler.dispose();
        }
        println("APF_FRONTEND_MAIN_OWNERSHIP_V6_TRACE_COMPLETE functions=" + functions.size());
    }
}
