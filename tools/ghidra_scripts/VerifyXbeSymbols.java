// Verify representative XbSymbolDatabase labels after focused XBE analysis.
// @category Xbox

import ghidra.app.script.GhidraScript;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class VerifyXbeSymbols extends GhidraScript {
    private Symbol requireSymbol(String name) {
        SymbolIterator symbols = currentProgram.getSymbolTable().getSymbols(name);
        if (!symbols.hasNext()) {
            throw new IllegalStateException("required signature label was not created: " + name);
        }
        return symbols.next();
    }

    @Override
    public void run() throws Exception {
        Symbol startup = requireSymbol("mainCRTStartup");
        Symbol swap = requireSymbol("D3DDevice_Swap");
        Symbol audio = requireSymbol("DirectSoundCreate");
        println("XBE_SYMBOL_TEST_PASS");
        println("mainCRTStartup=" + startup.getAddress() + " namespace=" + startup.getParentNamespace());
        println("D3DDevice_Swap=" + swap.getAddress() + " namespace=" + swap.getParentNamespace());
        println("DirectSoundCreate=" + audio.getAddress() + " namespace=" + audio.getParentNamespace());
    }
}
