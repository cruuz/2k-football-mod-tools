// Recovered Backbreaker Ghidra script.
//
// This source was reconstructed by CFR-decompiling the compiled .class
// artifact left in the Ghidra OSGi bundle cache; the original .java was not
// retained. Decompiler artifacts have been corrected and the script compiles
// cleanly against the vendored Ghidra 12.1.2 API plus the XEXLoaderWV
// extension (javac --release 21, zero errors). Run it only against a
// Backbreaker XEX whose MD5 matches EXPECTED_MD5 below.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;

public class BackbreakerTU2ActiveCameraTrace
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final Range[] RANGES = new Range[]{new Range(2183175296L, 2183175316L, "camera_active_fov_accessors"), new Range(2183176000L, 2183176204L, "camera_fov_derived_state_update"), new Range(2183176356L, 2183176632L, "shared_camera_constructor_tuning_excerpt"), new Range(2183177368L, 2183178932L, "shared_camera_per_frame_update"), new Range(2183179712L, 2183180172L, "shared_camera_rotation_input_smoothing"), new Range(2183365832L, 2183366204L, "camera_director_selection"), new Range(2184023264L, 2184023548L, "shared_camera_transform_accessors"), new Range(2184676008L, 2184676372L, "qb_camera_constructor"), new Range(2184676456L, 2184677116L, "qb_camera_transform_update"), new Range(2184677120L, 2184678088L, "qb_camera_gameplay_update")};
    private static final Word[] CRITICAL_WORDS = new Word[]{new Word(2183175296L, 2558724985L, "active-request byte writer object+0xB79"), new Word(2183175304L, 3491954948L, "FOV setter object+0x104"), new Word(2183175312L, 3223519492L, "FOV getter object+0x104"), new Word(2183176052L, 3227713796L, "consume FOV object+0x104 as floating argument three"), new Word(2183176152L, 1212270497L, "call derived camera-state builder 0x82626778"), new Word(2183176364L, 3284734076L, "load shared rotation smoothing rate 2.0"), new Word(2183176556L, 3554609968L, "store smoothing rate axis zero object+0xB30"), new Word(2183176560L, 3554609972L, "store smoothing rate axis one object+0xB34"), new Word(2183176564L, 3546221368L, "store default input scale 180 object+0xB38"), new Word(2183176568L, 3512666940L, "store default input scale 45 object+0xB3C"), new Word(2183176616L, 3542024452L, "store shared default FOV 65 object+0x104"), new Word(2183176672L, 3554607348L, "base ctor initializes selector-two height to 2.0"), new Word(2183177668L, 2172583936L, "load active camera vtable"), new Word(2183177676L, 2171273264L, "load per-frame vtable slot +0x30"), new Word(2183177684L, 1317012513L, "dispatch per-frame slot"), new Word(2183177904L, 1208805113L, "copy post-update camera matrix from object+0x40"), new Word(2183178048L, 2171273260L, "load post-effect matrix commit slot +0x2C"), new Word(2183178056L, 1317012513L, "commit post-effect camera matrix"), new Word(2183179840L, 3250522936L, "read axis-zero input scale object+0xB38"), new Word(2183179848L, 3248425788L, "read axis-one input scale object+0xB3C"), new Word(2183179876L, 3518958372L, "write axis-zero target delta object+0xB24"), new Word(2183179884L, 3491695404L, "write axis-one target delta object+0xB2C"), new Word(2183179972L, 3491695392L, "write smoothed axis-zero state object+0xB20"), new Word(2183180044L, 3491695400L, "write smoothed axis-one state object+0xB28"), new Word(2183365908L, 1274877805L, "director enables candidate camera"), new Word(2183365924L, 2171273272L, "director loads vtable slot +0x38"), new Word(2183365960L, 2171273268L, "director loads activation slot +0x34"), new Word(2184023264L, 962592912L, "vector destination object+0x90"), new Word(2184023312L, 962592896L, "vector destination object+0x80"), new Word(2184023360L, 962789440L, "matrix destination object+0x40"), new Word(2184676056L, 2441019392L, "install QB vtable 0x8205881C"), new Word(2184676168L, 3223915544L, "load QB FOV 90.0"), new Word(2184676184L, 1023443456L, "pin r8 base used by isolated FOV candidate"), new Word(2184676196L, 3248820348L, "load paired-block height 2.0"), new Word(2184676204L, 3246664668L, "load paired-block trailing offset -3.1"), new Word(2184676268L, 3518955740L, "store height in selector block zero"), new Word(2184676272L, 3516858592L, "store trailing offset in selector block zero"), new Word(2184676292L, 3518955764L, "store height in selector block one"), new Word(2184676296L, 3516858616L, "store trailing offset in selector block one"), new Word(2184676252L, 3493792568L, "store QB input scale 90 object+0xB38"), new Word(2184676256L, 3510569788L, "store QB input scale zero object+0xB3C"), new Word(2184676328L, 1273567393L, "call FOV setter"), new Word(2184676500L, 1208549517L, "activation transform calls selector 0x82408520"), new Word(2184676816L, 1274414913L, "activation transform writes vector object+0x80"), new Word(2184676864L, 2171273256L, "activation transform loads vector writer slot +0x28 for object+0x90"), new Word(2184676980L, 3225354632L, "activation transform reads tolerance/interpolation field object+0x188"), new Word(2184677052L, 1272843021L, "activation transform builds final view matrix"), new Word(2184677068L, 2171273260L, "activation transform loads final matrix commit slot +0x2C"), new Word(2184677148L, 2304969594L, "QB update activation guard object+0xB7A"), new Word(2184677168L, 1208548849L, "call selector 0x82408520"), new Word(2184677172L, 721616898L, "compare selector result with two"), new Word(2184677180L, 3284074724L, "load selector block one at object+0xE4"), new Word(2184677208L, 3284074700L, "load selector block zero at object+0xCC"), new Word(2184677680L, 2171076648L, "gameplay update loads vector writer slot +0x28 for object+0x90"), new Word(2184677716L, 1274414013L, "gameplay update writes vector object+0x80"), new Word(2184677824L, 3225354632L, "gameplay update reads tolerance/interpolation field object+0x188"), new Word(2184678040L, 1272842033L, "gameplay update builds final view matrix"), new Word(2184678056L, 2171273260L, "load final matrix commit slot +0x2C"), new Word(2184678064L, 1317012513L, "commit final camera matrix")};
    private static final long QB_VTABLE = 2181400604L;
    private static final long[] QB_VTABLE_EXPECTED = new long[]{2184676376L, 2183177368L, 2189539072L, 0x822D8D88L, 2184023416L, 2183557664L, 2183557672L, 2183557512L, 2187685400L, 2184023280L, 2184023264L, 2184023360L, 2184677120L, 2184676456L, 2183178936L, 2184675920L, 2187685400L, 2183175312L};
    private static final long[] XREF_TARGETS = new long[]{2181041176L, 2183175304L, 2183175312L, 2183176000L, 2184023264L, 2184023312L, 2184023360L, 2184023464L, 2184023520L, 2184677120L};

    private Address address(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private String bytes(Address start, int count) throws Exception {
        byte[] data = new byte[count];
        int read = this.currentProgram.getMemory().getBytes(start, data);
        if (read != count) {
            throw new IllegalStateException("short read at " + String.valueOf(start));
        }
        StringBuilder output = new StringBuilder();
        for (byte item : data) {
            output.append(String.format("%02X", item & 0xFF));
        }
        return output.toString();
    }

    private long unsignedWord(long target) throws Exception {
        return Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(this.address(target)));
    }

    private void validate() throws Exception {
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected Backbreaker TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        for (Word word : CRITICAL_WORDS) {
            long actual = this.unsignedWord(word.address);
            if (actual == word.expected) continue;
            throw new IllegalStateException("word mismatch at " + this.hex(word.address) + ": expected " + this.hex(word.expected) + ", found " + this.hex(actual));
        }
        for (int index = 0; index < QB_VTABLE_EXPECTED.length; ++index) {
            long slot = 2181400604L + (long)index * 4L;
            long actual = this.unsignedWord(slot);
            if (actual == QB_VTABLE_EXPECTED[index]) continue;
            throw new IllegalStateException("QB vtable mismatch at " + this.hex(slot) + ": expected " + this.hex(QB_VTABLE_EXPECTED[index]) + ", found " + this.hex(actual));
        }
        byte[] expectedName = "Quarterback Camera\u0000".getBytes(StandardCharsets.US_ASCII);
        byte[] actualName = new byte[expectedName.length];
        this.currentProgram.getMemory().getBytes(this.address(2181400676L), actualName);
        for (int index = 0; index < expectedName.length; ++index) {
            if (actualName[index] == expectedName[index]) continue;
            throw new IllegalStateException("QB class-name mismatch at 0x82058864");
        }
    }

    private void writeFacts(BufferedWriter output) throws Exception {
        output.write("Backbreaker TU2 active quarterback-camera facts\n");
        output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
        output.write("class_name=Quarterback Camera\n");
        output.write("class_name_va=0x82058864\n");
        output.write("qb_vtable=0x8205881C\n\n");
        output.write("CRITICAL_WORDS\n");
        for (Word word : CRITICAL_WORDS) {
            output.write(this.hex(word.address) + " " + this.hex(word.expected) + " " + word.meaning + "\n");
        }
        output.write("\nQB_VTABLE\n");
        for (int index = 0; index < QB_VTABLE_EXPECTED.length; ++index) {
            output.write(String.format("+0x%02X %s\n", index * 4, this.hex(QB_VTABLE_EXPECTED[index])));
        }
        output.write("\nREFERENCES_TO_CAMERA_HELPERS\n");
        for (long target : XREF_TARGETS) {
            output.write(this.hex(target) + "\n");
            ReferenceIterator references = this.currentProgram.getReferenceManager().getReferencesTo(this.address(target));
            while (references.hasNext()) {
                Reference reference = references.next();
                Function owner = this.currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
                String ownerText = owner == null ? "no_function" : owner.getName() + "@" + String.valueOf(owner.getEntryPoint());
                output.write("  " + String.valueOf(reference.getReferenceType()) + " from=" + String.valueOf(reference.getFromAddress()) + " owner=" + ownerText + "\n");
            }
        }
    }

    private void writeAssembly(BufferedWriter output, Range range) throws Exception {
        output.write("RANGE " + range.name + " " + this.hex(range.first) + ".." + this.hex(range.last) + "\n");
        for (long value = range.first; value <= range.last; value += 4L) {
            Instruction instruction;
            Address cursor = this.address(value);
            if (this.currentProgram.getListing().getInstructionAt(cursor) == null) {
                this.disassemble(cursor);
            }
            if ((instruction = this.currentProgram.getListing().getInstructionAt(cursor)) == null) {
                output.write(this.hex(value) + " " + this.bytes(cursor, 4) + " <UNDEFINED_XENON_WORD>\n");
                continue;
            }
            ArrayList<String> references = new ArrayList<String>();
            for (Reference reference : instruction.getReferencesFrom()) {
                references.add(String.valueOf(reference.getReferenceType()) + "->" + String.valueOf(reference.getToAddress()));
            }
            output.write(this.hex(value) + " " + this.bytes(cursor, instruction.getLength()) + " " + instruction.toString().replace('\t', ' ') + (String)(references.isEmpty() ? "" : " refs=" + String.join(";", references)) + "\n");
        }
        output.write("\n");
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerTU2ActiveCameraTrace.java OUTPUT_DIRECTORY");
        }
        this.validate();
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_active_camera_facts.txt")))) {
            this.writeFacts(output);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_active_camera_assembly.txt")))) {
            output.write("Backbreaker TU2 bounded active-camera assembly\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            output.write("Undefined words are Xenon vector opcodes unsupported by Ghidra's A2 language; bytes are unchanged.\n\n");
            for (Range range : RANGES) {
                this.writeAssembly(output, range);
            }
        }
        this.println("BACKBREAKER_TU2_ACTIVE_CAMERA_TRACE_COMPLETE output=" + String.valueOf(directory));
    }

    private static final class Word {
        final long address;
        final long expected;
        final String meaning;

        Word(long address, long expected, String meaning) {
            this.address = address;
            this.expected = expected;
            this.meaning = meaning;
        }
    }

    private static final class Range {
        final long first;
        final long last;
        final String name;

        Range(long first, long last, String name) {
            this.first = first;
            this.last = last;
            this.name = name;
        }
    }
}

