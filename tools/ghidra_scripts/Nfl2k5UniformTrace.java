// Trace NFL 2K5 Unif registration, loading, relocation, and consumers.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
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
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5UniformTrace extends GhidraScript {
    // Little-endian scalar interpretation of ASCII bytes "Unif".
    private static final long UNIF_SCALAR = 0x66696E55L;

    // Explicitly proved uniform-path functions.  getFunctionContaining() is
    // intentional: several evidence addresses are calls inside larger owners.
    private static final long[] FOCUS = {
        0x00038570L, 0x00038580L, 0x000385C0L, 0x00038650L,
        0x000436A0L, 0x000436F0L, 0x00043D20L, 0x00043E10L,
        0x000449E0L, 0x000615A0L, 0x00063270L, 0x0007BD91L,
        0x00078D40L, 0x00078DD0L,
        0x0008E830L, 0x0008E840L, 0x0008E850L, 0x0008E860L,
        0x0008E870L, 0x0008E880L, 0x0008E9E0L, 0x0008EFA0L,
        0x0008FAD0L, 0x00090570L, 0x0011A0ACL,
        0x00166420L, 0x00166450L, 0x00166490L, 0x001664B0L,
        0x000E3530L, 0x001C20B0L, 0x001C20F0L, 0x001C2140L,
    };

    // Inclusive byte ranges retain callback bodies and the exact instructions
    // around interior evidence addresses even when Ghidra has no function.
    private static final long[][] RANGES = {
        {0x00038570L, 0x000386B0L},
        {0x00043D20L, 0x00043DA7L},
        {0x000615A0L, 0x00061703L},
        {0x00063260L, 0x000632A3L},
        {0x00078D40L, 0x00078E40L},
        {0x0007BD80L, 0x0007BE0AL},
        {0x0008E830L, 0x0008E8CBL},
        {0x000905A0L, 0x00090640L},
        {0x000E3530L, 0x000E36B9L},
        {0x0011A0A0L, 0x0011A0FFL},
        {0x00166400L, 0x001664B9L},
        {0x001C20B0L, 0x001C22B9L},
    };

    private String addr(Address address) {
        if (address == null) return "";
        return address.isMemoryAddress()
            ? String.format("0x%08X", address.getUnsignedOffset()) : address.toString();
    }

    private String section(Address address) {
        MemoryBlock block = currentProgram.getMemory().getBlock(address);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private String relations(Set<Function> functions) {
        List<String> result = new ArrayList<>();
        for (Function function : sorted(functions)) result.add(functionName(function));
        return String.join(";", result);
    }

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", value & 0xFF));
        }
        return result.toString();
    }

    private List<Address> findBytes(byte[] needle) throws Exception {
        List<Address> hits = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                cursor = hit.add(1);
            }
        }
        return hits;
    }

    private void addOwner(Set<Function> functions, Function owner) {
        if (owner == null) return;
        functions.add(owner);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: Nfl2k5UniformTrace.java OUTPUT_DIRECTORY");
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        File traceFile = new File(directory, "uniform_trace.txt");
        File pseudoFile = new File(directory, "uniform_focused_pseudo_c.c");
        File disassemblyFile = new File(directory, "uniform_focused_disassembly.txt");
        Set<Function> functions = new LinkedHashSet<>();
        List<Address> missingFocus = new ArrayList<>();

        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 Unif static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Constraint: field names remain provisional unless tied to an exact instruction.\n\n");

            List<Address> hits = findBytes("Unif".getBytes(StandardCharsets.US_ASCII));
            trace.write("RAW_Unif count=" + hits.size() + " scalar=0x66696E55\n");
            for (Address hit : hits) {
                Function containing = currentProgram.getFunctionManager().getFunctionContaining(hit);
                addOwner(functions, containing);
                List<String> references = new ArrayList<>();
                ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(hit);
                while (refs.hasNext()) {
                    Reference reference = refs.next();
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                        reference.getFromAddress());
                    addOwner(functions, owner);
                    references.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + ")");
                }
                trace.write(addr(hit) + " section=" + section(hit) +
                    " containing=" + functionName(containing) +
                    " references=" + String.join(";", references) + "\n");
            }

            trace.write("\nSCALAR_Unif\n");
            int scalarCount = 0;
            InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (!(object instanceof Scalar)) continue;
                        if (((Scalar)object).getUnsignedValue() != UNIF_SCALAR) continue;
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                            instruction.getAddress());
                        addOwner(functions, owner);
                        trace.write(addr(instruction.getAddress()) + " bytes=" +
                            bytes(instruction) + " instruction=" + instruction +
                            " owner=" + functionName(owner) + "\n");
                        scalarCount++;
                    }
                }
            }
            trace.write("SCALAR_Unif_COUNT=" + scalarCount + "\n\n");

            trace.write("FOCUS_FUNCTIONS\n");
            for (long value : FOCUS) {
                Address address = toAddr(value);
                Function function = currentProgram.getFunctionManager().getFunctionContaining(address);
                if (function == null) {
                    trace.write(addr(address) + " MISSING\n");
                    missingFocus.add(address);
                    continue;
                }
                addOwner(functions, function);
                trace.write(addr(address) + " owner=" + functionName(function) + "\n");
            }
            for (Function function : sorted(functions)) {
                trace.write(functionName(function) + " section=" + section(function.getEntryPoint()) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + "\n");
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile));
             BufferedWriter disassembly = new BufferedWriter(new FileWriter(disassemblyFile))) {
            pseudo.write("/* NFL 2K5 Unif focused pseudo-C; recovered types remain provisional. */\n\n");
            for (Address address : missingFocus) {
                pseudo.write("// PORTME: could not decompile function at " + addr(address) +
                    "; Ghidra has no defined function there; exact instructions are retained " +
                    "in uniform_focused_disassembly.txt.\n");
            }
            if (!missingFocus.isEmpty()) pseudo.write("\n");
            disassembly.write("NFL 2K5 Unif focused disassembly\n\n");
            disassembly.write("EXACT_EVIDENCE_RANGES\n");
            for (long[] range : RANGES) {
                Address start = toAddr(range[0]);
                Address end = toAddr(range[1]);
                disassembly.write(addr(start) + "-" + addr(end) + "\n");
                InstructionIterator evidence = currentProgram.getListing().getInstructions(
                    new AddressSet(start, end), true);
                while (evidence.hasNext()) {
                    Instruction instruction = evidence.next();
                    disassembly.write(addr(instruction.getAddress()) + "  " +
                        bytes(instruction) + "  " + instruction + "\n");
                }
                disassembly.write("\n");
            }
            disassembly.write("FOCUSED_FUNCTIONS\n\n");
            for (Function function : sorted(functions)) {
                pseudo.write("/* " + functionName(function) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + " */\n");
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

                disassembly.write(functionName(function) + "\n");
                InstructionIterator body = currentProgram.getListing().getInstructions(
                    function.getBody(), true);
                while (body.hasNext()) {
                    Instruction instruction = body.next();
                    disassembly.write(addr(instruction.getAddress()) + "  " +
                        bytes(instruction) + "  " + instruction + "\n");
                }
                disassembly.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL2K5_UNIFORM_TRACE_COMPLETE functions=" + functions.size());
    }
}
