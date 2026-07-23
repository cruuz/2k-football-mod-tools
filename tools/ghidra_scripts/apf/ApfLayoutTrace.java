// Trace the APF 2K8 LAYT loader, record lookup, transform access, and draw gate.
// @category Xbox360.APF2K8

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
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfLayoutTrace extends GhidraScript {
    private static final long LAYT_HASH = 0x86A1AC9EL;
    private static final long LAYOUT_MAINMENU_HASH = 0x48C6D154L;
    private static final long FRONTEND_SYNC_HASH = 0xF69D21E4L;
    private static final long TIMELINE_SECONDS_PER_FRAME = 0x82000E94L;

    private static final long[] FOCUS = {
        0x84686680L, // instant-replay mutually-exclusive record draw gate
        0x84694038L, // template_menulayout lookup/init
        0x846EC9A8L, // field-local relative-pointer relocation
        0x846ED638L, // runtime +0x3c handler-object dispatch, event path A
        0x846ED698L, // runtime +0x3c handler-object dispatch, event path B
        0x846EDBC8L, // recursive record lookup, including type-2 child layouts
        0x846EDC98L, // type-0 lookup wrapper
        0x846EDD30L, // type-0 timeline/progress update and phase classification
        0x846EDEA8L, // type-3 frame descriptor copied into type-0 timeline
        0x846EEC98L, // type-0 runtime bit-29 setter
        0x846EED58L, // returns selected record +0x10
        0x846EF8A0L, // linked-record relocation walk
        0x846EF940L, // typed linked-record relocation dispatch
        0x8475A920L, // keyboard LAYT setup
        0x8475AC48L, // mutates selected type-0 +0x14 offset
        0x84B16398L  // generic asset lookup used with LAYT hash
    };

    private static final long[][] RANGES = {
        {0x84686680L, 0x84686747L},
        {0x84694038L, 0x8469415FL},
        {0x846EC9A8L, 0x846ECA4BL},
        {0x846ED638L, 0x846ED6F7L},
        {0x846EDAE8L, 0x846EED8FL},
        {0x846EF8A0L, 0x846EFA9BL},
        {0x8475A920L, 0x8475AD4BL}
    };

    private String addr(Address address) {
        return address == null ? "" : String.format("0x%08X", address.getUnsignedOffset());
    }

    private String functionName(Function function) {
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private String section(Address address) {
        MemoryBlock block = currentProgram.getMemory().getBlock(address);
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

    private boolean hasHalfword(Instruction instruction, int wanted) {
        for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
            for (Object object : instruction.getOpObjects(operand)) {
                if (object instanceof Scalar &&
                    ((((Scalar)object).getUnsignedValue() & 0xffffL) == wanted)) return true;
            }
        }
        return false;
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private void traceConstantOwners(BufferedWriter stream, long value,
            Set<Function> functions) throws Exception {
        int high = (int)((value >>> 16) & 0xffff);
        int adjustedHigh = (int)(((value + 0x8000L) >>> 16) & 0xffff);
        int low = (int)(value & 0xffff);
        Set<Function> highOwners = new LinkedHashSet<>();
        Set<Function> adjustedHighOwners = new LinkedHashSet<>();
        Set<Function> lowOwners = new LinkedHashSet<>();
        List<Instruction> highHits = new ArrayList<>();
        List<Instruction> adjustedHighHits = new ArrayList<>();
        List<Instruction> lowHits = new ArrayList<>();
        InstructionIterator iterator = currentProgram.getListing().getInstructions(true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            if (owner == null) continue;
            if (hasHalfword(instruction, high)) {
                highOwners.add(owner);
                highHits.add(instruction);
            }
            if (hasHalfword(instruction, adjustedHigh)) {
                adjustedHighOwners.add(owner);
                adjustedHighHits.add(instruction);
            }
            if (hasHalfword(instruction, low)) {
                lowOwners.add(owner);
                lowHits.add(instruction);
            }
        }
        Set<Function> both = new LinkedHashSet<>(highOwners);
        both.addAll(adjustedHighOwners);
        both.retainAll(lowOwners);
        functions.addAll(both);
        stream.write(String.format(
            "CONSTANT 0x%08X high=0x%04X adjusted_high=0x%04X low=0x%04X\n",
            value, high, adjustedHigh, low));
        stream.write("owners_with_both_halves=");
        List<String> names = new ArrayList<>();
        for (Function function : sorted(both)) names.add(functionName(function));
        stream.write(String.join(";", names) + "\n");
        stream.write("high_owner_count=" + highOwners.size() +
            " adjusted_high_owner_count=" + adjustedHighOwners.size() +
            " low_owner_count=" + lowOwners.size() + "\n");
        stream.write("high_hits=");
        List<String> hitText = new ArrayList<>();
        for (Instruction hit : highHits) hitText.add(addr(hit.getAddress()) + ":" + hit);
        stream.write(String.join(";", hitText) + "\n");
        stream.write("adjusted_high_hits=");
        hitText.clear();
        for (Instruction hit : adjustedHighHits) hitText.add(addr(hit.getAddress()) + ":" + hit);
        stream.write(String.join(";", hitText) + "\n");
        stream.write("low_hits=");
        hitText.clear();
        for (Instruction hit : lowHits) hitText.add(addr(hit.getAddress()) + ":" + hit);
        stream.write(String.join(";", hitText) + "\n\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfLayoutTrace.java OUTPUT_DIRECTORY");
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }
        Set<Function> functions = new LinkedHashSet<>();
        File traceFile = new File(output, "layout_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 LAYT focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Program language: " + currentProgram.getLanguageID() + "\n");
            trace.write("Constraint: a split PPC immediate is attributed only when both halves " +
                "occur in one defined function; this still does not name a field by itself.\n\n");

            traceConstantOwners(trace, LAYT_HASH, functions);
            traceConstantOwners(trace, LAYOUT_MAINMENU_HASH, functions);
            traceConstantOwners(trace, FRONTEND_SYNC_HASH, functions);
            int timelineRaw = currentProgram.getMemory().getInt(
                toAddr(TIMELINE_SECONDS_PER_FRAME));
            trace.write(String.format(
                "TIMELINE_CONSTANT 0x%08X raw=0x%08X float=%.9g refs=%s\n\n",
                TIMELINE_SECONDS_PER_FRAME, timelineRaw,
                Float.intBitsToFloat(timelineRaw),
                String.join(";", referencesTo(toAddr(TIMELINE_SECONDS_PER_FRAME)))));

            trace.write("FOCUS\n");
            for (long value : FOCUS) {
                Address address = toAddr(value);
                Function function = currentProgram.getFunctionManager().getFunctionContaining(address);
                if (function != null) functions.add(function);
                trace.write(addr(address) + " section=" + section(address) + " owner=" +
                    functionName(function) + " refs=" + String.join(";", referencesTo(address)) +
                    "\n");
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "layout_focused_pseudo_c.c");
        File disassemblyFile = new File(output, "layout_focused_disassembly.txt");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile));
             BufferedWriter disassembly = new BufferedWriter(new FileWriter(disassemblyFile))) {
            pseudo.write("/* APF 2K8 LAYT focused pseudo-C; semantic claims require exact consumers. */\n\n");
            disassembly.write("APF 2K8 LAYT exact evidence ranges\n\n");
            for (long[] range : RANGES) {
                Address start = toAddr(range[0]);
                Address end = toAddr(range[1]);
                disassembly.write(addr(start) + "-" + addr(end) + "\n");
                InstructionIterator iterator = currentProgram.getListing().getInstructions(
                    new AddressSet(start, end), true);
                while (iterator.hasNext()) {
                    Instruction instruction = iterator.next();
                    disassembly.write(addr(instruction.getAddress()) + "  " +
                        bytes(instruction) + "  " + instruction + "\n");
                }
                disassembly.write("\n");
            }
            for (Function function : sorted(functions)) {
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 30 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        addr(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_LAYOUT_TRACE_COMPLETE functions=" + functions.size());
    }
}
