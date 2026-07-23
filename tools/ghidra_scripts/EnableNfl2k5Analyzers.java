// Ensure the two XBE-specific analyzers are enabled without disabling Ghidra's
// normal x86 recovery passes.  This script is intentionally NFL-specific so a
// headless import command cannot accidentally alter the APF project.
// @category Xbox.NFL2K5

import ghidra.app.script.GhidraScript;

public class EnableNfl2k5Analyzers extends GhidraScript {
    private static final String SYMBOL_ANALYZER = "Xbox Symbol Database Analyzer";
    private static final String XTLID_ANALYZER = "Xbox XTLID Symbol ID Analyzer";

    @Override
    public void run() throws Exception {
        setAnalysisOption(currentProgram, SYMBOL_ANALYZER, "true");
        setAnalysisOption(currentProgram, XTLID_ANALYZER, "true");
        println("NFL2K5_ANALYZERS_ENABLED: " + SYMBOL_ANALYZER + ", " + XTLID_ANALYZER);
    }
}
