// Emit read-only instruction/data evidence for APF's entry-shell indirect calls.
// @category VisualConcepts.StaticRecomp

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfBootIndirectFrontier extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[] CALL_SITES = {
        0x8468CF4CL, 0x84BDAA00L,
        0x84BDAFA0L, 0x84BDDF90L, 0x84BDE678L, 0x84BDE7E4L,
        0x84BDE878L, 0x84BDE8ACL, 0x84BDEB28L, 0x84BDEB60L,
        0x84BEBDECL, 0x84BF0C94L, 0x84BF1724L, 0x84BF1760L,
        0x84BF17ACL, 0x84BF1824L, 0x84BF198CL
    };

    private static final long[] XREF_TARGETS = {
        0x82000940L, 0x844D1B0CL, 0x84D10000L, 0x84D10010L,
        0x84D103E4L, 0x84F01540L, 0x84F02440L, 0x852D5C24L,
        0x852D5DBCL, 0x852D5DCCL, 0x852D5DD0L, 0x852D5DD4L,
        0x852D5DD8L, 0x852D6464L
    };

    private static final long[][] WORD_RANGES = {
        {0x844D1B0CL, 0x844D1B10L},
        {0x84D10000L, 0x84D1000CL},
        {0x84D10010L, 0x84D103E0L},
        {0x84D103E4L, 0x84D103F0L},
        {0x852D5C24L, 0x852D5C28L},
        {0x852D5DBCL, 0x852D5DDCL},
        {0x852D6464L, 0x852D6468L}
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", value & 0xff));
        }
        return result.toString();
    }

    private String owner(Address value) {
        Function function = currentProgram.getFunctionManager().getFunctionContaining(value);
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            values.add(hex(reference.getFromAddress().getUnsignedOffset()) + ":" +
                owner(reference.getFromAddress()) + ":" + reference.getReferenceType());
        }
        values.sort(String::compareTo);
        return values;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfBootIndirectFrontier.java OUTPUT_FILE");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + md5);
        }
        File outputFile = new File(args[0]);
        File parent = outputFile.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }

        try (BufferedWriter output = new BufferedWriter(new FileWriter(outputFile))) {
            output.write("record\taddress\tvalue_or_bytes\tdetail\n");
            for (long callSite : CALL_SITES) {
                Address cursor = address(callSite);
                Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
                if (instruction == null) {
                    disassemble(cursor);
                    instruction = currentProgram.getListing().getInstructionAt(cursor);
                }
                if (instruction == null) {
                    throw new IllegalStateException("missing instruction at " + hex(callSite));
                }
                output.write("call\t" + hex(callSite) + "\t" + bytes(instruction) +
                    "\t" + instruction.toString() + ";owner=" + owner(cursor) + "\n");
            }
            for (long[] range : WORD_RANGES) {
                for (long cursor = range[0]; cursor < range[1]; cursor += 4) {
                    Address valueAddress = address(cursor);
                    long value = Integer.toUnsignedLong(
                        currentProgram.getMemory().getInt(valueAddress));
                    output.write("word\t" + hex(cursor) + "\t" + hex(value) +
                        "\tsection=" + section(valueAddress) + "\n");
                }
            }
            for (long target : XREF_TARGETS) {
                Address targetAddress = address(target);
                List<String> references = referencesTo(targetAddress);
                output.write("xrefs\t" + hex(target) + "\t" + references.size() +
                    "\t" + String.join(";", references) + "\n");
            }
        }
    }
}
