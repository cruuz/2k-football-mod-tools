// Emit instruction-, byte-, flow-, reference-, and p-code-level evidence for
// NFL 2K5 functions that the C decompiler cannot finish.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressRangeIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryAccessException;
import ghidra.program.model.pcode.PcodeOp;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5HardFunctionReport extends GhidraScript {
    private String addr(Address address) {
        if (address == null) return "none";
        return address.isMemoryAddress()
            ? String.format("0x%08X", address.getUnsignedOffset())
            : address.toString();
    }

    private String bytes(Instruction instruction) {
        try {
            byte[] raw = instruction.getBytes();
            StringBuilder value = new StringBuilder();
            for (byte b : raw) value.append(String.format("%02X", b & 0xff));
            return value.toString();
        }
        catch (MemoryAccessException error) {
            return "<unreadable:" + error.getMessage() + ">";
        }
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        String namespace = function.getParentNamespace() == null || function.getParentNamespace().isGlobal()
            ? "" : function.getParentNamespace().getName(true) + "::";
        return addr(function.getEntryPoint()) + ":" + namespace + function.getName();
    }

    private String functions(Iterable<Function> values) {
        List<Function> sorted = new ArrayList<>();
        for (Function function : values) sorted.add(function);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        List<String> names = new ArrayList<>();
        for (Function function : sorted) names.add(functionName(function));
        return String.join(";", names);
    }

    private String bodyRanges(Function function) {
        List<String> ranges = new ArrayList<>();
        AddressRangeIterator iterator = function.getBody().getAddressRanges();
        while (iterator.hasNext()) {
            AddressRange range = iterator.next();
            ranges.add(addr(range.getMinAddress()) + "-" + addr(range.getMaxAddress()));
        }
        return String.join(";", ranges);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException(
                "usage: Nfl2k5HardFunctionReport.java OUTPUT_FILE ADDRESS [ADDRESS ...]");
        }
        File output = new File(args[0]);
        File parent = output.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }

        try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
            writer.write("NFL 2K5 hard-function evidence\n");
            writer.write("program=" + currentProgram.getName() + "\n\n");

            for (int i = 1; i < args.length; i++) {
                long offset = Long.decode(args[i]);
                Address requested = toAddr(offset);
                Function function = currentProgram.getFunctionManager().getFunctionAt(requested);
                if (function == null) function = currentProgram.getFunctionManager().getFunctionContaining(requested);
                writer.write("requested=" + addr(requested) + "\n");
                if (function == null) {
                    writer.write("PORTME: no recovered function contains requested address\n\n");
                    continue;
                }

                writer.write("function=" + functionName(function) + "\n");
                writer.write("body_ranges=" + bodyRanges(function) + "\n");
                writer.write("body_size=" + function.getBody().getNumAddresses() + "\n");
                writer.write("signature=" + function.getSignature() + "\n");
                writer.write("calling_convention=" + function.getCallingConventionName() + "\n");
                writer.write("callers=" + functions(function.getCallingFunctions(monitor)) + "\n");
                writer.write("callees=" + functions(function.getCalledFunctions(monitor)) + "\n");
                writer.write("entry_references_to:\n");
                ReferenceIterator entryReferences =
                    currentProgram.getReferenceManager().getReferencesTo(function.getEntryPoint());
                while (entryReferences.hasNext()) {
                    Reference reference = entryReferences.next();
                    writer.write("  ref " + reference.getReferenceType() + " " +
                        addr(reference.getFromAddress()) + " -> " + addr(reference.getToAddress()) +
                        " source=" + reference.getSource() + "\n");
                }
                writer.write("instructions:\n");

                InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    writer.write(addr(instruction.getAddress()) + "  " + bytes(instruction) + "  " + instruction);
                    writer.write("  fallthrough=" + addr(instruction.getFallThrough()));
                    Address[] flows = instruction.getFlows();
                    List<String> flowValues = new ArrayList<>();
                    for (Address flow : flows) flowValues.add(addr(flow));
                    writer.write("  flows=" + String.join(",", flowValues));
                    writer.write("\n");
                    for (Reference reference : instruction.getReferencesFrom()) {
                        writer.write("    ref " + reference.getReferenceType() + " " +
                            addr(reference.getFromAddress()) + " -> " + addr(reference.getToAddress()) +
                            " source=" + reference.getSource() + "\n");
                    }
                    PcodeOp[] pcode = instruction.getPcode();
                    for (PcodeOp op : pcode) writer.write("    pcode " + op + "\n");
                }
                writer.write("\n");
            }
        }
        println("NFL2K5_HARD_FUNCTION_REPORT_COMPLETE output=" + output + " targets=" + (args.length - 1));
    }
}
