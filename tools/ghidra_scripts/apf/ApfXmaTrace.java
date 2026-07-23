// Read-only APF 2K8 XMA import reference and caller trace.
// @category Xbox.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfXmaTrace extends GhidraScript {
    private static final Map<String, Long> TARGETS = new LinkedHashMap<>();
    static {
        TARGETS.put("XMAReleaseContext_IAT", 0x8200078CL);
        TARGETS.put("XMACreateContext_IAT", 0x82000790L);
        TARGETS.put("XMAReleaseContext_thunk", 0x84D088BCL);
        TARGETS.put("XMACreateContext_thunk", 0x84D088CCL);
    }
    private static final long[][] CALLER_RANGES = {
        {0x84BF7B40L, 0x84BF7BC8L},
        {0x84BF8740L, 0x84BF8890L},
    };

    private String addr(Address value) {
        return value == null ? "none" : String.format("0x%08X", value.getUnsignedOffset());
    }

    private String owner(Address address) {
        Function function = currentProgram.getFunctionManager().getFunctionContaining(address);
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private String block(Address address) {
        MemoryBlock value = currentProgram.getMemory().getBlock(address);
        return value == null ? "none" : value.getName();
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException(
            "usage: ApfXmaTrace.java OUTPUT_DIRECTORY");
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }
        File reportPath = new File(output, "xma_import_trace.txt");
        File pseudoPath = new File(output, "xma_candidate_pseudo_c.c");
        Set<Function> candidates = new LinkedHashSet<>();

        try (BufferedWriter report = new BufferedWriter(new FileWriter(reportPath))) {
            report.write("APF 2K8 XMA import reference trace\n");
            report.write("Executable MD5: " + currentProgram.getExecutableMD5() + "\n");
            report.write("Constraint: import reachability does not by itself name AUDO fields.\n\n");

            for (Map.Entry<String, Long> target : TARGETS.entrySet()) {
                Address address = toAddr(target.getValue());
                Instruction targetInstruction = currentProgram.getListing().getInstructionAt(address);
                report.write("TARGET " + target.getKey() + " " + addr(address) +
                    " block=" + block(address) + " owner=" + owner(address) +
                    " instruction=" + (targetInstruction == null ? "none" : targetInstruction) +
                    " bytes=");
                for (int byteIndex = 0; byteIndex < 16; byteIndex++) {
                    report.write(String.format("%02X",
                        currentProgram.getMemory().getByte(address.add(byteIndex)) & 0xff));
                }
                report.write("\n");
                ReferenceIterator incoming = currentProgram.getReferenceManager().getReferencesTo(address);
                int count = 0;
                while (incoming.hasNext()) {
                    Reference reference = incoming.next();
                    Function function = currentProgram.getFunctionManager().getFunctionContaining(
                        reference.getFromAddress());
                    if (function != null) candidates.add(function);
                    report.write("  " + reference.getReferenceType() + " " +
                        addr(reference.getFromAddress()) + " -> " + addr(reference.getToAddress()) +
                        " source=" + reference.getSource() + " owner=" +
                        owner(reference.getFromAddress()) + "\n");
                    count++;
                }
                report.write("  incoming_count=" + count + "\n\n");
            }

            report.write("ALL_INSTRUCTION_REFERENCES_TO_TARGETS\n");
            InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                for (Reference reference : instruction.getReferencesFrom()) {
                    long destination = reference.getToAddress().getUnsignedOffset();
                    String label = null;
                    for (Map.Entry<String, Long> target : TARGETS.entrySet()) {
                        if (destination == target.getValue()) label = target.getKey();
                    }
                    if (label == null) continue;
                    Function function = currentProgram.getFunctionManager().getFunctionContaining(
                        instruction.getAddress());
                    if (function != null) candidates.add(function);
                    report.write(label + " " + addr(instruction.getAddress()) + " " +
                        instruction + " ref=" + reference.getReferenceType() + " owner=" +
                        owner(instruction.getAddress()) + "\n");
                }
                for (Address flow : instruction.getFlows()) {
                    String label = null;
                    for (Map.Entry<String, Long> target : TARGETS.entrySet()) {
                        if (flow.getUnsignedOffset() == target.getValue()) label = target.getKey();
                    }
                    if (label == null) continue;
                    Function function = currentProgram.getFunctionManager().getFunctionContaining(
                        instruction.getAddress());
                    if (function != null) candidates.add(function);
                    report.write(label + " " + addr(instruction.getAddress()) + " " +
                        instruction + " flow owner=" + owner(instruction.getAddress()) + "\n");
                }
            }

            report.write("\nRAW_PPC_BRANCHES_TO_TARGETS\n");
            for (MemoryBlock memoryBlock : currentProgram.getMemory().getBlocks()) {
                if (!memoryBlock.isInitialized() || !memoryBlock.isExecute()) continue;
                long start = memoryBlock.getStart().getUnsignedOffset();
                long end = memoryBlock.getEnd().getUnsignedOffset();
                start = (start + 3L) & ~3L;
                for (long pc = start; pc + 3 <= end; pc += 4) {
                    Address instructionAddress = toAddr(pc);
                    long word = currentProgram.getMemory().getInt(instructionAddress) & 0xFFFFFFFFL;
                    long opcode = word >>> 26;
                    long destination = -1;
                    if (opcode == 18) {
                        long displacement = word & 0x03FFFFFCL;
                        if ((displacement & 0x02000000L) != 0) displacement |= ~0x03FFFFFFL;
                        destination = (word & 0x2L) != 0 ? displacement : pc + displacement;
                    }
                    else if (opcode == 16) {
                        long displacement = word & 0x0000FFFCL;
                        if ((displacement & 0x00008000L) != 0) displacement |= ~0x0000FFFFL;
                        destination = (word & 0x2L) != 0 ? displacement : pc + displacement;
                    }
                    destination &= 0xFFFFFFFFL;
                    String label = null;
                    for (Map.Entry<String, Long> target : TARGETS.entrySet()) {
                        if (destination == target.getValue()) label = target.getKey();
                    }
                    if (label == null) continue;
                    Function function = currentProgram.getFunctionManager().getFunctionContaining(
                        instructionAddress);
                    if (function != null) candidates.add(function);
                    report.write(label + " " + addr(instructionAddress) +
                        " raw=" + String.format("%08X", word) +
                        " lk=" + (word & 1L) + " owner=" + owner(instructionAddress) + "\n");
                }
            }

            report.write("\nPDATA_CALLER_RANGE_DISASSEMBLY\n");
            for (long[] range : CALLER_RANGES) {
                report.write("RANGE " + String.format("0x%08X", range[0]) + "-" +
                    String.format("0x%08X", range[1] - 1) + "\n");
                for (long pc = range[0]; pc < range[1]; pc += 4) {
                    Address address = toAddr(pc);
                    long word = currentProgram.getMemory().getInt(address) & 0xFFFFFFFFL;
                    Instruction instruction = currentProgram.getListing().getInstructionAt(address);
                    report.write(addr(address) + " " + String.format("%08X", word) + " " +
                        (instruction == null ? "<not-disassembled>" : instruction.toString()) + "\n");
                }
                report.write("\n");
            }

            List<Function> ordered = new ArrayList<>(candidates);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            report.write("\nCANDIDATES count=" + ordered.size() + "\n");
            for (Function function : ordered) {
                report.write(addr(function.getEntryPoint()) + ":" + function.getName() +
                    " body=" + function.getBody() + "\n");
            }

            DecompInterface decompiler = new DecompInterface();
            decompiler.openProgram(currentProgram);
            try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoPath))) {
                pseudo.write("/* APF XMA import-reference candidate pseudo-C. */\n\n");
                for (Function function : ordered) {
                    DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                    pseudo.write("/* " + addr(function.getEntryPoint()) + " " +
                        function.getName() + " */\n");
                    if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                        pseudo.write(result.getDecompiledFunction().getC());
                    }
                    else {
                        pseudo.write("// PORTME: decompilation failed: " +
                            result.getErrorMessage().replace('\n', ' ') + "\n");
                    }
                    pseudo.write("\n");
                }
            }
            decompiler.dispose();
        }
        println("APF_XMA_TRACE_COMPLETE output=" + output);
    }
}
