// Keep an XBE signature-validation run focused and reproducible.
// @category Xbox

import java.util.Map;

import ghidra.app.script.GhidraScript;

public class OnlyXbeAnalyzers extends GhidraScript {
    private static final String SYMBOL_ANALYZER = "Xbox Symbol Database Analyzer";
    private static final String XTLID_ANALYZER = "Xbox XTLID Symbol ID Analyzer";

    @Override
    public void run() throws Exception {
        Map<String, String> options = getCurrentAnalysisOptionsAndValues(currentProgram);
        for (Map.Entry<String, String> option : options.entrySet()) {
            if ("true".equalsIgnoreCase(option.getValue())) {
                setAnalysisOption(currentProgram, option.getKey(), "false");
            }
        }
        setAnalysisOption(currentProgram, SYMBOL_ANALYZER, "true");
        setAnalysisOption(currentProgram, XTLID_ANALYZER, "true");
        println("Enabled only: " + SYMBOL_ANALYZER + ", " + XTLID_ANALYZER);
    }
}
