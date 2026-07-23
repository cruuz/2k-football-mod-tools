// Report memory, bytes, code-unit, and references around arbitrary NFL 2K5 addresses.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5AddressEvidence extends GhidraScript {
    private String addr(Address value) {
        return value == null ? "none" : String.format("0x%08X", value.getUnsignedOffset());
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) throw new IllegalArgumentException(
            "usage: Nfl2k5AddressEvidence.java OUTPUT_FILE ADDRESS [ADDRESS ...]");
        File output = new File(args[0]);
        File parent = output.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
            for (int i = 1; i < args.length; i++) {
                Address address = toAddr(Long.decode(args[i]));
                MemoryBlock block = currentProgram.getMemory().getBlock(address);
                Function function = currentProgram.getFunctionManager().getFunctionContaining(address);
                CodeUnit code = currentProgram.getListing().getCodeUnitContaining(address);
                writer.write("address=" + addr(address) + "\n");
                writer.write("block=" + (block == null ? "none" : block.getName()) +
                    " read=" + (block != null && block.isRead()) +
                    " write=" + (block != null && block.isWrite()) +
                    " execute=" + (block != null && block.isExecute()) + "\n");
                writer.write("function=" + (function == null ? "none" :
                    addr(function.getEntryPoint()) + ":" + function.getName()) + "\n");
                writer.write("code_unit=" + (code == null ? "none" :
                    addr(code.getAddress()) + ":" + code.toString()) + "\n");
                writer.write("bytes[-16,+31]=");
                Address start = address.subtract(16);
                for (int offset = 0; offset < 48; offset++) {
                    Address cursor = start.add(offset);
                    if (currentProgram.getMemory().contains(cursor)) {
                        writer.write(String.format("%02X", currentProgram.getMemory().getByte(cursor) & 0xff));
                    }
                    else writer.write("??");
                }
                writer.write("\nreferences_from:\n");
                if (code instanceof Instruction) {
                    for (Reference reference : ((Instruction)code).getReferencesFrom()) {
                        writer.write("  " + reference.getReferenceType() + " " +
                            addr(reference.getFromAddress()) + " -> " + addr(reference.getToAddress()) +
                            " source=" + reference.getSource() + "\n");
                    }
                }
                writer.write("references_to:\n");
                ReferenceIterator incoming = currentProgram.getReferenceManager().getReferencesTo(address);
                while (incoming.hasNext()) {
                    Reference reference = incoming.next();
                    writer.write("  " + reference.getReferenceType() + " " +
                        addr(reference.getFromAddress()) + " -> " + addr(reference.getToAddress()) +
                        " source=" + reference.getSource() + "\n");
                }
                writer.write("\n");
            }
        }
        println("NFL2K5_ADDRESS_EVIDENCE_COMPLETE output=" + output + " targets=" + (args.length - 1));
    }
}
