// Recovered Backbreaker Ghidra script.
//
// This source was reconstructed by CFR-decompiling the compiled .class
// artifact left in the Ghidra OSGi bundle cache; the original .java was not
// retained. Decompiler artifacts have been corrected and the script compiles
// cleanly against the vendored Ghidra 12.1.2 API plus the XEXLoaderWV
// extension (javac --release 21, zero errors). Run it only against a
// Backbreaker XEX whose MD5 matches EXPECTED_MD5 below.

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.util.LinkedHashSet;

public class BackbreakerTU2TransitionPolicy
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final String[] DEFINE_NAMES = new String[]{"INVALID", "AERIAL", "BOMB", "BALL_LOCK", "BLOCK", "BULLET", "CATCH", "CHASE", "CHARGE", "CINEMATIC", "CORNERBACK", "CUT_TURN", "TURN", "DEBUG", "DEFENSIVE", "EVASION", "FAIR_CATCH", "CELEBRATION", "FIELDGOAL_CINEMATIC", "INTERCEPTED", "INTERCEPTION", "FREE_FLIGHT", "WIDE_RECEIVER", "OUT_OF_ACTION", "PLAYER_SWITCH", "FOCUS", "OVERVIEW", "PLAY_START", "QUARTERBACK", "QUARTERBACK_FOCUS", "READY", "READY_NO_AUDIBLE", "QUARTERBACK_READY", "AUDIBLE", "BALL_LOCK_AUDIBLE", "SHOWBOAT", "TACKLE", "TACKLING", "KICKING", "KICKING_NO_AUDIBLE", "KICK_RETURN", "KICK_RETURN_PRE_SNAP", "KICK_RETURN_CINEMATIC", "END_OF_PLAY", "JUMBOTRON", "PAUSE", "TIMEOUT", "LOOSE_BALL", "TEST", "REPLAY_1", "REPLAY_2", "REPLAY_3", "REPLAY_4", "REPLAY_5", "CUTSCENE_ANIM", "TA_INTRO", "CUTSCENE_HUDDLE", "ZONING", "ZONING_PRESNAP", "CUTSCENE_WARMUP"};

    private Address a(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private long u8(long value) throws Exception {
        return Byte.toUnsignedLong(this.currentProgram.getMemory().getByte(this.a(value)));
    }

    private long u16(long value) throws Exception {
        return Short.toUnsignedLong(this.currentProgram.getMemory().getShort(this.a(value)));
    }

    private long u32(long value) throws Exception {
        return Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(this.a(value)));
    }

    private String h(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private void dumpFunction(long entry, DecompInterface decompiler) throws Exception {
        int count;
        Function f = this.currentProgram.getFunctionManager().getFunctionAt(this.a(entry));
        if (f == null) {
            f = this.currentProgram.getFunctionManager().getFunctionContaining(this.a(entry));
        }
        if (f == null) {
            this.println("FUNCTION_MISSING " + this.h(entry));
            return;
        }
        this.println("FUNCTION " + f.getName() + " " + String.valueOf(f.getEntryPoint()) + ".." + String.valueOf(f.getBody().getMaxAddress()));
        DecompileResults results = decompiler.decompileFunction(f, 180, this.monitor);
        if (results.decompileCompleted() && results.getDecompiledFunction() != null) {
            this.println("PSEUDO_C_BEGIN " + this.h(entry));
            this.println(results.getDecompiledFunction().getC());
            this.println("PSEUDO_C_END " + this.h(entry));
        } else {
            this.println("DECOMPILE_FAILED " + this.h(entry) + " " + results.getErrorMessage());
        }
        this.println("ASSEMBLY_BEGIN " + this.h(entry));
        Instruction ins = this.currentProgram.getListing().getInstructionAt(f.getEntryPoint());
        for (count = 0; ins != null && f.getBody().contains(ins.getAddress()) && count < 5000; ins = ins.getNext(), ++count) {
            this.println(String.valueOf(ins.getAddress()) + " " + this.h(this.u32(ins.getAddress().getOffset())) + " " + ins.toString().replace('\t', ' '));
        }
        this.println("ASSEMBLY_END " + this.h(entry) + " count=" + count);
    }

    private void dumpDirectorWords() throws Exception {
        this.println("DIRECTOR_CONSTRUCTOR_WORDS_BEGIN");
        for (long p = 2183357008L; p < 2183357584L; p += 4L) {
            this.println(this.h(p) + " " + this.h(this.u32(p)));
        }
        this.println("DIRECTOR_CONSTRUCTOR_WORDS_END");
    }

    private void dumpRawRange(String label, long start, long end) throws Exception {
        this.println(label + "_BEGIN");
        for (long p = start; p < end; p += 4L) {
            Instruction ins = this.currentProgram.getListing().getInstructionAt(this.a(p));
            String decoded = ins == null ? "<UNDEFINED>" : ins.toString().replace('\t', ' ');
            this.println(this.h(p) + " " + this.h(this.u32(p)) + " " + decoded);
        }
        this.println(label + "_END");
    }

    private void dumpObjectFocusWindows() throws Exception {
        long[][] windows = new long[][]{{2183360012L, 2183360100L}, {2183360144L, 2183360188L}, {2183360936L, 2183361024L}, {2183361288L, 2183361684L}, {2183361812L, 2183361856L}, {2183362208L, 2183362460L}};
        for (int i = 0; i < windows.length; ++i) {
            this.dumpRawRange("OBJECT_PASS_FOCUS_RAW_" + i, windows[i][0], windows[i][1]);
        }
    }

    private void dumpCallSites(long callee) throws Exception {
        this.println("MODE_REQUEST_CALL_SITES_BEGIN");
        ReferenceIterator refs = this.currentProgram.getReferenceManager().getReferencesTo(this.a(callee));
        block0: while (refs.hasNext()) {
            Reference ref = (Reference)refs.next();
            Address from = ref.getFromAddress();
            Instruction call = this.currentProgram.getListing().getInstructionAt(from);
            this.println("CALL_SITE " + String.valueOf(from) + " type=" + String.valueOf(ref.getReferenceType()));
            Instruction first = call;
            for (int i = 0; i < 10 && first != null; first = first.getPrevious(), ++i) {
            }
            Instruction ins = first;
            for (int count = 0; ins != null && count < 14; ins = ins.getNext(), ++count) {
                this.println(String.valueOf(ins.getAddress()) + " " + this.h(this.u32(ins.getAddress().getOffset())) + " " + ins.toString().replace('\t', ' '));
                if (ins.getAddress().equals((Object)from)) continue block0;
            }
        }
        this.println("MODE_REQUEST_CALL_SITES_END");
    }

    private void dumpExecutableZeroCaves(int minimumBytes) throws Exception {
        this.println("EXECUTABLE_ZERO_CAVES_BEGIN minimum=" + minimumBytes);
        Memory memory = this.currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isExecute() || !block.isInitialized()) continue;
            long runStart = -1L;
            long runLength = 0L;
            long start = block.getStart().getOffset();
            long end = block.getEnd().getOffset();
            for (long p = start; p <= end; ++p) {
                boolean zero;
                boolean bl = zero = memory.getByte(this.a(p)) == 0;
                if (zero) {
                    if (runLength == 0L) {
                        runStart = p;
                    }
                    ++runLength;
                }
                if (zero && p != end || runLength == 0L) continue;
                if (runLength >= (long)minimumBytes) {
                    this.println("ZERO_CAVE start=" + this.h(runStart) + " length=" + runLength + " end=" + this.h(runStart + runLength - 1L) + " block=" + block.getName());
                }
                runLength = 0L;
                runStart = -1L;
            }
        }
        this.println("EXECUTABLE_ZERO_CAVES_END");
    }

    protected void run() throws Exception {
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 MD5 " + this.currentProgram.getExecutableMD5());
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(this.currentProgram);
        this.println("CAMERA_DEFINE_TABLE_BEGIN");
        for (int id = 1; id <= 59; ++id) {
            long policyTarget;
            if (id == 1) {
                policyTarget = 2183358764L;
            } else {
                long selector = this.u8(2181178752L + (long)(id - 2));
                policyTarget = 2183358548L + selector * 4L;
            }
            long objectOffset = this.u16(2181178816L + (long)(id - 1) * 2L);
            long objectTarget = 2183359048L + objectOffset;
            this.println(String.format("ID %02d %-26s policy_target=%s object_target=%s object_jump_offset=0x%04X", id, DEFINE_NAMES[id], this.h(policyTarget), this.h(objectTarget), objectOffset));
        }
        this.println("CAMERA_DEFINE_TABLE_END");
        long[] functions = new long[]{2183358400L, 2183358472L, 2183358976L, 2183357008L, 2183468640L, 2184183896L};
        LinkedHashSet<Long> seen = new LinkedHashSet<Long>();
        for (long entry : functions) {
            long actual;
            Function f = this.currentProgram.getFunctionManager().getFunctionAt(this.a(entry));
            if (f == null) {
                f = this.currentProgram.getFunctionManager().getFunctionContaining(this.a(entry));
            }
            long l = actual = f == null ? entry : f.getEntryPoint().getOffset();
            if (!seen.add(actual)) continue;
            this.dumpFunction(entry, decompiler);
        }
        this.dumpDirectorWords();
        this.dumpRawRange("TRANSITION_POLICY_RAW", 2183358472L, 2183358976L);
        this.dumpRawRange("DIRECTOR_RUNTIME_CONSTRUCTOR_RAW", 2183367136L, 2183367712L);
        this.dumpObjectFocusWindows();
        this.dumpCallSites(2183363504L);
        this.dumpExecutableZeroCaves(16);
        decompiler.dispose();
        this.println("BACKBREAKER_TU2_TRANSITION_POLICY_COMPLETE");
    }
}

