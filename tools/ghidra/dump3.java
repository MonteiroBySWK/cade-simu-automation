// dump3.java — decompila as funções que referenciam endereços dados (formatos).
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;

public class dump3 extends GhidraScript {
    public void run() throws Exception {
        Program p = currentProgram;
        FunctionManager fm = p.getFunctionManager();
        long[] alvos = {0x00b60d58L, 0x00b4cc64L, 0x00b723c4L, 0x00b6f5e0L, 0x00b7534cL, 0x00b73144L};
        java.util.LinkedHashSet<Function> fns = new java.util.LinkedHashSet<>();
        for (long a : alvos) {
            Address ad = toAddr(a);
            Reference[] refs = getReferencesTo(ad);
            println("### refs to " + ad + " : " + refs.length);
            for (Reference r : refs) {
                Function f = fm.getFunctionContaining(r.getFromAddress());
                if (f != null) { fns.add(f); println("   " + f.getName() + " @" + f.getEntryPoint()); }
            }
        }
        DecompInterface di = new DecompInterface();
        di.openProgram(p);
        int i = 0;
        for (Function f : fns) {
            if (++i > 8) break;
            println("\n===== DECOMP " + f.getName() + " @" + f.getEntryPoint());
            DecompileResults res = di.decompileFunction(f, 90, monitor);
            if (res != null && res.decompileCompleted()) {
                String[] lines = res.getDecompiledFunction().getC().split("\n");
                for (int k = 0; k < Math.min(lines.length, 130); k++) println(lines[k]);
            } else {
                println("(falha)");
            }
        }
    }
}
