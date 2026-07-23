// Remove one analyzer-created false function only after proving that its entire
// body is zero-filled, non-executable data with no callers, callees, or inbound
// references. The script refuses to change the project if any guard fails.
// @category Xbox.NFL2K5

import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressIterator;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class Nfl2k5RejectZeroDataFunction extends GhidraScript {
    private void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: Nfl2k5RejectZeroDataFunction.java ADDRESS");
        }
        Address entry = toAddr(Long.decode(args[0]));
        FunctionManager functions = currentProgram.getFunctionManager();
        Function function = functions.getFunctionAt(entry);
        require(function != null, "no exact function at " + entry);
        MemoryBlock block = currentProgram.getMemory().getBlock(entry);
        require(block != null, "no memory block contains " + entry);
        // The XBE loader conservatively marks .data executable, so the section
        // name plus the stronger byte/reference guards below are authoritative.
        require(".data".equals(block.getName()) || !block.isExecute(),
            "refusing to remove function outside .data/non-executable memory: " + block.getName());
        require(function.getCallingFunctions(monitor).isEmpty(), "function has callers");
        require(function.getCalledFunctions(monitor).isEmpty(), "function has callees");
        List<CodeUnit> falseSourceInstructions = new ArrayList<>();
        ReferenceIterator references = currentProgram.getReferenceManager().getReferencesTo(entry);
        while (references.hasNext()) {
            Reference reference = references.next();
            Address source = reference.getFromAddress();
            MemoryBlock sourceBlock = currentProgram.getMemory().getBlock(source);
            CodeUnit sourceCode = currentProgram.getListing().getCodeUnitContaining(source);
            require(sourceBlock != null && ".data".equals(sourceBlock.getName()),
                "inbound reference originates outside .data at " + source);
            require(currentProgram.getFunctionManager().getFunctionContaining(source) == null,
                "inbound reference originates in a recovered function at " + source);
            require(reference.getSource() == SourceType.DEFAULT,
                "inbound reference is not analyzer-default at " + source);
            require(sourceCode instanceof Instruction,
                "inbound reference source is not a false instruction at " + source);
            falseSourceInstructions.add(sourceCode);
        }
        AddressIterator bodyAddresses = function.getBody().getAddresses(true);
        while (bodyAddresses.hasNext()) {
            Address address = bodyAddresses.next();
            require(currentProgram.getMemory().getByte(address) == 0,
                "nonzero byte in candidate body at " + address);
        }

        Address bodyMin = function.getBody().getMinAddress();
        Address bodyMax = function.getBody().getMaxAddress();
        long bodySize = function.getBody().getNumAddresses();
        int transaction = currentProgram.startTransaction("Reject zero-filled .data false function");
        boolean commit = false;
        try {
            for (CodeUnit sourceCode : falseSourceInstructions) {
                currentProgram.getListing().clearCodeUnits(
                    sourceCode.getMinAddress(), sourceCode.getMaxAddress(), false);
            }
            require(functions.removeFunction(entry), "FunctionManager refused to remove " + entry);
            currentProgram.getListing().clearCodeUnits(bodyMin, bodyMax, false);
            commit = true;
        }
        finally {
            currentProgram.endTransaction(transaction, commit);
        }
        println("NFL2K5_REJECT_ZERO_DATA_FUNCTION_COMPLETE address=" + entry +
            " block=" + block.getName() + " bytes=" + bodySize +
            " false_inbound_instructions=" + falseSourceInstructions.size());
    }
}
