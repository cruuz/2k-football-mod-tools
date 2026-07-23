// Promote four statically proven TXTR callbacks that generic analysis left as
// LAB_ labels.  Boundaries were verified from control-flow, RET/tail-JMP
// endings, alignment padding, and the next recovered function.
// @category Xbox.NFL2K5

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class Nfl2k5RecoverTxtrCallbacks extends GhidraScript {
    private static final long[][] RANGES = {
        {0x00044BB0L, 0x00044C03L},
        {0x00044DF0L, 0x00044E51L},
        {0x00044F10L, 0x00044F84L},
        {0x00045000L, 0x0004500DL}
    };

    @Override
    protected void run() throws Exception {
        int created = 0;
        int existing = 0;
        for (long[] range : RANGES) {
            Address start = toAddr(range[0]);
            Address end = toAddr(range[1]);
            Function function = currentProgram.getFunctionManager().getFunctionAt(start);
            if (function != null) {
                existing++;
                println("NFL2K5_TXTR_CALLBACK_EXISTS " + start + " " + function.getName());
                continue;
            }
            String name = String.format("FUN_%08x", range[0]);
            function = currentProgram.getFunctionManager().createFunction(
                name, start, new AddressSet(start, end), SourceType.ANALYSIS);
            function.setComment(
                "Recovered TXTR-chain callback/handler. Boundary evidence: aligned referenced entry, " +
                "terminal RET or tail-JMP, padding, and next function start. See " +
                "research/functions/nfl2k5/focused/txtr_focused_disassembly.txt.");
            created++;
            println("NFL2K5_TXTR_CALLBACK_CREATED " + start + "-" + end + " " + function.getName());
        }
        println("NFL2K5_TXTR_CALLBACK_RECOVERY_COMPLETE created=" + created + " existing=" + existing);
    }
}
