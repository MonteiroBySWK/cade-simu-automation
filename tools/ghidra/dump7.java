// dump7.java — localiza a checagem de senha (Clave.cpp, "4962").
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class dump7 extends GhidraScript {
    public void run() throws Exception {
        Program p = currentProgram;
        FunctionManager fm = p.getFunctionManager();
        Listing st = p.getListing();
        String[] alvo = {"4962", "senha correta", "clave correcta", "palavra-chave", "palabra clave",
                         "Error Clave", "clave de acceso", "Clave"};
        java.util.LinkedHashSet<Function> fns = new java.util.LinkedHashSet<>();
        for (Data d : st.getDefinedData(true)) {
            Object v = null;
            try { v = d.getValue(); } catch (Exception e) { }
            if (v == null) continue;
            String s = v.toString();
            boolean hit = false;
            for (String q : alvo) if (s.contains(q)) hit = true;
            if (!hit) continue;
            println("STR " + d.getAddress() + " [" + s.replace("\n", " ").substring(0, Math.min(60, s.length())) + "]");
            for (Reference r : getReferencesTo(d.getAddress())) {
                Function f = fm.getFunctionContaining(r.getFromAddress());
                if (f != null) {
                    fns.add(f);
                    println("    xref -> " + f.getName() + " @" + f.getEntryPoint() + "  (from " + r.getFromAddress() + ")");
                }
            }
        }
        DecompInterface di = new DecompInterface();
        di.openProgram(p);
        int i = 0;
        for (Function f : fns) {
            if (++i > 4) break;
            println("\n===== DECOMP " + f.getName() + " @" + f.getEntryPoint());
            DecompileResults res = di.decompileFunction(f, 90, monitor);
            if (res != null && res.decompileCompleted()) {
                for (String ln : res.getDecompiledFunction().getC().split("\n")) println(ln);
            } else println("(falha)");
        }
    }
}
