// Emit exact read-only evidence for APF 2K8 navigation-label rendering.
// @category VisualConcepts.Menu

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
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfMenuLabelRendererV3 extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[][] RANGES = {
        {0x846F2748L, 0x846F2978L}, // generic descriptor event callback.
        {0x846F2E00L, 0x846F3090L}, // Main Menu event callback and jump table.
        {0x846F3090L, 0x846F3258L}, // common event predecessor, full PDATA extent.
        {0x846F3568L, 0x846F3E40L}, // every pre-construction runtime-row accessor caller.
        {0x846F4988L, 0x846F4A6CL}, // first runtime-label getter consumer.
        {0x846F5198L, 0x846F52B4L}, // quicknav runtime-label getter consumers.
        {0x846F4028L, 0x846F4168L}, // Main row callback pass and materializer.
        {0x846F55E8L, 0x846F5638L}, // Main-specific row-construction wrapper.
        {0x846F62E8L, 0x846F64D8L}, // row cache and widget construction entry.
        {0x846F6618L, 0x846F69D0L}, // widget creation and callback binding.
        {0x846F69D0L, 0x846F6C38L}, // first text render callback.
        {0x846F9090L, 0x846F9360L}, // event dispatch and descriptor callback call.
        {0x846FAB10L, 0x846FAB40L}, // widget lookup.
        {0x846FB370L, 0x846FB3B0L}, // callback/user-data setters.
        {0x846FBCF0L, 0x846FBD30L}, // widget mode setter.
        {0x846933C0L, 0x84693478L}, // normal run draw/finalization.
        {0x84693478L, 0x84693538L}, // highlighted run draw, full PDATA extent.
        {0x84A58698L, 0x84A586DCL}, // End Of Game / Quit return-to-Main callback.
        {0x84A352B0L, 0x84A35368L}, // game-specific runtime-label getter consumer.
        {0x84B43498L, 0x84B434DCL}, // bounded UTF-16 copy helper.
        {0x84B646C0L, 0x84B64780L}, // UTF-16 formatter string-argument writer.
        {0x84B65B00L, 0x84B65B70L}  // bounded UTF-16 formatting wrapper.
    };

    private static final long[] FOCUS = {
        0x846F06F0L, 0x846F0708L, 0x846F3888L,
        0x846F2748L, 0x846F2E00L, 0x846F3090L,
        0x846F40B8L, 0x846F4988L, 0x846F5198L, 0x846F55E8L,
        0x846F62E8L, 0x846F6618L,
        0x846F69D0L, 0x846F6C38L, 0x846FAB28L,
        0x846FB380L, 0x846FB388L, 0x846FB390L, 0x846FB3A0L,
        0x846FBCF0L, 0x846933C0L, 0x84693478L, 0x84B43498L,
        0x84A352B0L, 0x84A58698L, 0x84B646C0L, 0x84B65B00L
    };

    private static final long[] STATIC_TARGETS = {
        0x820F4350L, 0x84E57340L,
        0x8460BFCCL, 0x8460BFE4L, 0x8460BFF0L, 0x8460C000L,
        0x8460C014L, 0x8460C024L, 0x8460C038L,
        0x844E0F90L, 0x844E0FA8L, 0x844E0FD8L, 0x844E0FF0L,
        0x844E10A8L, 0x844E10D8L, 0x844E1168L, 0x844E1190L,
        0x844F35F8L, 0x844FAC20L,
        0x845210B8L, 0x84521154L,
        0x84D302C8L, 0x84D30328L, 0x84D30400L, 0x84D30458L,
        0x820F4800L, 0x84E588C0L, 0x84E58AA0L
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

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", value & 0xff));
        }
        return result.toString();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
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

    private void writeTarget(BufferedWriter output, long value, Set<Function> functions)
            throws Exception {
        Address target = address(value);
        Function at = currentProgram.getFunctionManager().getFunctionAt(target);
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(target);
        if (owner != null) functions.add(owner);
        output.write(hex(value) + " section=" + section(target) +
            " function_at=" + functionName(at) + " owner=" + functionName(owner) +
            " refs=" + String.join(";", referencesTo(target)) + "\n");
    }

    private void writeRange(BufferedWriter output, long first, long afterLast,
            Set<Function> functions) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast - 1) + "\n");
        long value = first;
        while (value < afterLast) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                // This only changes the transient listing opened with -readOnly. It neither
                // creates a saved function nor writes the project or executable.
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(value) + " <no instruction> // PORTME: inline data or " +
                    "decoder rejected the bytes\n");
                value += 4;
                continue;
            }
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(cursor);
            if (owner != null) functions.add(owner);
            output.write(hex(value) + " " + bytes(instruction) + " " + instruction +
                " owner=" + functionName(owner) + " refs=" +
                String.join(";", referencesTo(cursor)) + "\n");
            value = instruction.getMaxAddress().getUnsignedOffset() + 1;
        }
        output.write("\n");
    }

    private void writeBytes(BufferedWriter output, long first, int count) throws Exception {
        byte[] data = new byte[count];
        Memory memory = currentProgram.getMemory();
        int read = memory.getBytes(address(first), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(first));
        StringBuilder text = new StringBuilder();
        for (byte value : data) text.append(String.format("%02x", value & 0xff));
        output.write(hex(first) + " length=" + count + " bytes=" + text + "\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfMenuLabelRendererV3.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + md5);
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        Set<Function> functions = new LinkedHashSet<>();

        File traceFile = new File(directory, "apf_menu_label_renderer_v3_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 menu-label renderer read-only v3 trace\n");
            trace.write("Program MD5: " + md5 + "\n");
            trace.write("No saved function, label, datatype, or program byte is created or " +
                "changed; transient disassembly is discarded by -readOnly.\n\n");

            trace.write("FOCUS\n");
            for (long value : FOCUS) writeTarget(trace, value, functions);
            trace.write("\nSTATIC_TARGETS\n");
            for (long value : STATIC_TARGETS) writeTarget(trace, value, functions);
            trace.write("\nSTATIC_BYTES\n");
            writeBytes(trace, 0x820F4350L, 0x48);
            writeBytes(trace, 0x84E57340L, 0x2A0);
            writeBytes(trace, 0x844E0F80L, 0x40);
            writeBytes(trace, 0x844E0FD0L, 0x30);
            writeBytes(trace, 0x844E10A0L, 0x48);
            writeBytes(trace, 0x844E1158L, 0x50);
            writeBytes(trace, 0x844F35F0L, 0x18);
            writeBytes(trace, 0x844FAC18L, 0x18);
            writeBytes(trace, 0x845210B8L, 0x20);
            writeBytes(trace, 0x84521154L, 0x28);
            writeBytes(trace, 0x84D302C8L, 0x120);
            writeBytes(trace, 0x84D30400L, 0x6C);
            writeBytes(trace, 0x820F4800L, 0x48);
            writeBytes(trace, 0x84E588C0L, 0x240);
            trace.write("\nINSTRUCTIONS\n");
            for (long[] range : RANGES) writeRange(trace, range[0], range[1], functions);
            trace.write("POST_DISASSEMBLY_REFERENCES\n");
            for (long value : FOCUS) writeTarget(trace, value, functions);
        }

        List<Function> sorted = new ArrayList<>(functions);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "apf_menu_label_renderer_v3_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* Saved-boundary APF menu-label pseudo-C; truncated PDATA " +
                "boundaries remain explicit. */\n\n");
            for (long value : FOCUS) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                if (function == null) {
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; Ghidra has no saved function boundary at this entry.\n");
                }
            }
            pseudo.write("\n");
            for (Function function : sorted) {
                pseudo.write("/* " + functionName(function) + " body=" +
                    hex(function.getBody().getMinAddress().getUnsignedOffset()) + ".." +
                    hex(function.getBody().getMaxAddress().getUnsignedOffset()) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 60 seconds" :
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
        println("APF_MENU_LABEL_RENDERER_V3_TRACE_COMPLETE saved_functions=" +
            functions.size());
    }
}
