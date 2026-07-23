// Emit compact machine-readable reconnaissance data from a loaded APF XEX.

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class ApfReconReport extends GhidraScript {
    private static String json(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\': out.append("\\\\"); break;
                case '"': out.append("\\\""); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int)c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.append('"').toString();
    }

    private static String hex(long value) {
        return String.format("0x%08X", value);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfReconReport.java OUTPUT_DIRECTORY");
        }
        File outputDirectory = new File(args[0]);
        if (!outputDirectory.isDirectory()) {
            throw new IllegalArgumentException("output directory does not exist");
        }

        Memory memory = currentProgram.getMemory();
        MemoryBlock[] blocks = memory.getBlocks();
        long textFunctions = 0;
        MemoryBlock text = memory.getBlock(".text");
        for (Function function : currentProgram.getFunctionManager().getFunctions(true)) {
            if (text != null && text.contains(function.getEntryPoint())) {
                textFunctions++;
            }
        }

        List<Symbol> imports = new ArrayList<>();
        SymbolIterator symbols = currentProgram.getSymbolTable().getAllSymbols(true);
        while (symbols.hasNext()) {
            Symbol symbol = symbols.next();
            if (symbol.getName().startsWith("__imp__")) {
                imports.add(symbol);
            }
        }
        imports.sort(Comparator.comparing(Symbol::getAddress));

        File jsonFile = new File(outputDirectory, "apf2k8_ghidra_program.json");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(jsonFile))) {
            writer.write("{\n");
            writer.write("  \"program_name\": " + json(currentProgram.getName()) + ",\n");
            writer.write("  \"executable_path\": " +
                json(currentProgram.getExecutablePath()) + ",\n");
            writer.write("  \"executable_format\": " +
                json(currentProgram.getExecutableFormat()) + ",\n");
            writer.write("  \"md5\": " +
                json(currentProgram.getExecutableMD5()) + ",\n");
            writer.write("  \"language_id\": " +
                json(currentProgram.getLanguageID().toString()) + ",\n");
            writer.write("  \"compiler_spec_id\": " +
                json(currentProgram.getCompilerSpec().getCompilerSpecID().toString()) + ",\n");
            writer.write("  \"program_image_base_property\": " +
                json(currentProgram.getImageBase().toString()) + ",\n");
            writer.write("  \"minimum_loaded_address\": " +
                json(memory.getMinAddress().toString()) + ",\n");
            writer.write("  \"function_count\": " +
                currentProgram.getFunctionManager().getFunctionCount() + ",\n");
            writer.write("  \"text_function_count\": " + textFunctions + ",\n");
            writer.write("  \"import_reference_symbol_count\": " + imports.size() + ",\n");
            writer.write("  \"memory_blocks\": [\n");
            for (int i = 0; i < blocks.length; i++) {
                MemoryBlock block = blocks[i];
                writer.write("    {\"name\": " + json(block.getName()) +
                    ", \"start\": " + json(block.getStart().toString()) +
                    ", \"end\": " + json(block.getEnd().toString()) +
                    ", \"size\": " + block.getSize() +
                    ", \"read\": " + block.isRead() +
                    ", \"write\": " + block.isWrite() +
                    ", \"execute\": " + block.isExecute() + "}");
                writer.write(i + 1 == blocks.length ? "\n" : ",\n");
            }
            writer.write("  ]\n}\n");
        }

        File importFile = new File(outputDirectory, "apf2k8_ghidra_imports.tsv");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(importFile))) {
            writer.write("address\traw_word\ttype\tordinal\tname\tsource\n");
            for (Symbol symbol : imports) {
                Address address = symbol.getAddress();
                int word = memory.getInt(address);
                int type = (word >>> 24) & 0xff;
                int ordinal = word & 0xffff;
                writer.write(hex(address.getUnsignedOffset()) + "\t" +
                    hex(Integer.toUnsignedLong(word)) + "\t" + type + "\t" +
                    ordinal + "\t" + symbol.getName() + "\t" +
                    symbol.getSource().toString() + "\n");
            }
        }

        println("Wrote " + jsonFile + " and " + importFile);
    }
}
