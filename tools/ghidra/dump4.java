// dump4.java — acha o PARSER (sscanf) e a montagem de netlist.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class dump4 extends GhidraScript {
    public void run() throws Exception {
        Program p = currentProgram;
        FunctionManager fm = p.getFunctionManager();
        Listing st = p.getListing();
        String[] alvo = {"*%d*%d", "%d#%s", "%2s", "%%", "*%1d*", "%d*%d*%d*%d*%d*%d*%d*%d"};
        java.util.LinkedHashSet<Function> fns = new java.util.LinkedHashSet<>();
        println("=== STRINGS de parse");
        for (Data d : st.getDefinedData(true)) {
            Object v = null;
            try { v = d.getValue(); } catch (Exception e) { }
            if (v == null) continue;
            String s = v.toString();
            boolean hit = false;
            for (String q : alvo) if (s.contains(q)) hit = true;
            if (!hit) continue;
            println("STR " + d.getAddress() + " " + s.replace("\n", " ").replace("\r", " "));
            for (Reference r : getReferencesTo(d.getAddress())) {
                Function f = fm.getFunctionContaining(r.getFromAddress());
                if (f != null) { fns.add(f); println("    xref -> " + f.getName() + " @" + f.getEntryPoint()); }
            }
        }
        DecompInterface di = new DecompInterface();
        di.openProgram(p);
        int i = 0;
        for (Function f : fns) {
            if (++i > 6) break;
            println("\n===== DECOMP " + f.getName() + " @" + f.getEntryPoint());
            DecompileResults res = di.decompileFunction(f, 90, monitor);
            if (res != null && res.decompileCompleted()) {
                String[] lines = res.getDecompiledFunction().getC().split("\n");
                for (int k = 0; k < Math.min(lines.length, 120); k++) println(lines[k]);
            } else println("(falha)");
        }
    }
}
