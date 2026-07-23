// Recovered Backbreaker Ghidra script.
//
// This source was reconstructed by CFR-decompiling the compiled .class
// artifact left in the Ghidra OSGi bundle cache; the original .java was not
// retained. Decompiler artifacts have been corrected and the script compiles
// cleanly against the vendored Ghidra 12.1.2 API plus the XEXLoaderWV
// extension (javac --release 21, zero errors). Run it only against a
// Backbreaker XEX whose MD5 matches EXPECTED_MD5 below.

import ghidra.app.script.GhidraScript;
import ghidra.app.util.Option;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.OpenOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import xexloaderwv.XEXHeader;
import xexloaderwv.XEXLoaderWVLoader;

public class BackbreakerApplyXexpDump
extends GhidraScript {
    private static final String BASE_SHA256 = "130f4ca5f0076c2895ce47961d255c5f90c6ec06f02742dfb7fc9e0e1680c347";
    private static final String XEXP_SHA256 = "8511013dd9bedb114b7fbfeadfb780c631e0e26e2ec1946f11d680e4ea91784a";

    private String sha256(byte[] data) throws Exception {
        byte[] value = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder output = new StringBuilder();
        for (byte item : value) {
            output.append(String.format("%02x", item & 0xFF));
        }
        return output.toString();
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length < 3 || args.length > 4) {
            throw new IllegalArgumentException("usage: BackbreakerApplyXexpDump.java BASE_XEX XEXP OUTPUT_PE_IMAGE [OUTPUT_RECONSTRUCTED_XEX]");
        }
        Path basePath = Path.of(args[0], new String[0]).toAbsolutePath().normalize();
        Path patchPath = Path.of(args[1], new String[0]).toAbsolutePath().normalize();
        Path outputPath = Path.of(args[2], new String[0]).toAbsolutePath().normalize();
        Path reconstructedPath = args.length == 4 ? Path.of(args[3], new String[0]).toAbsolutePath().normalize() : null;
        byte[] base = Files.readAllBytes(basePath);
        byte[] patch = Files.readAllBytes(patchPath);
        if (!BASE_SHA256.equals(this.sha256(base))) {
            throw new IllegalStateException("unexpected base XEX SHA-256 " + this.sha256(base));
        }
        if (!XEXP_SHA256.equals(this.sha256(patch))) {
            throw new IllegalStateException("unexpected XEXP SHA-256 " + this.sha256(patch));
        }
        if (outputPath.equals(basePath) || outputPath.equals(patchPath) || reconstructedPath != null && (reconstructedPath.equals(basePath) || reconstructedPath.equals(patchPath) || reconstructedPath.equals(outputPath))) {
            throw new IllegalArgumentException("output must not replace an input");
        }
        File parent = outputPath.toFile().getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(parent));
        }
        ArrayList<Option> options = new ArrayList<Option>();
        options.add(new Option("Process .pdata", (Object)true));
        options.add(new Option("Load PDB File", (Object)false));
        options.add(new Option("use experimental PDB loader", (Object)false));
        options.add(new Option("Path to xexp", (Object)patchPath.toString()));
        XEXLoaderWVLoader loader = new XEXLoaderWVLoader();
        byte[] patchedXex = loader.ApplyPatch(base, patchPath.toString(), options, false);
        XEXHeader finalHeader = new XEXHeader(patchedXex, options, false);
        byte[] image = finalHeader.peImage;
        if (image == null || image.length < 2 || image[0] != 77 || image[1] != 90) {
            throw new IllegalStateException("patched result is not an MZ memory image");
        }
        Files.write(outputPath, image, new OpenOption[0]);
        if (reconstructedPath != null) {
            File reconstructedParent = reconstructedPath.toFile().getParentFile();
            if (reconstructedParent != null && !reconstructedParent.isDirectory() && !reconstructedParent.mkdirs()) {
                throw new IllegalStateException("cannot create " + String.valueOf(reconstructedParent));
            }
            Files.write(reconstructedPath, patchedXex, new OpenOption[0]);
        }
        this.println("BACKBREAKER_XEXP_DUMP_COMPLETE output=" + String.valueOf(outputPath) + " bytes=" + image.length + " sha256=" + this.sha256(image) + (String)(reconstructedPath == null ? "" : " reconstructed_xex=" + String.valueOf(reconstructedPath) + " reconstructed_sha256=" + this.sha256(patchedXex)) + " image_base=" + String.format("0x%08X", finalHeader.imageBaseAddress) + " entry=" + String.format("0x%08X", finalHeader.entryPointAddress));
    }
}

