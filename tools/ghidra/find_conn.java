// Ghidra Java postScript — mapeia a conectividade/serialização do CADe_SIMU.
// Uso: analyzeHeadless <proj> <name> -process <bin> -noanalysis -scriptPath tools/ghidra -postScript find_conn.java
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class find_conn extends GhidraScript {
    public void run() throws Exception {
        Program p = currentProgram;
        FunctionManager fm = p.getFunctionManager();
        Listing st = p.getListing();
        println("=== PROGRAMA: " + p.getName());
        String[] pad = {"CADe_SIMU*", "Simula", "Conect", "Cable", ".Serial", "Dibujo",
                        "Libreria", "Nudo", "Nodo", "Enlazar", "Unir"};
        println("=== STRINGS-CHAVE");
        int n = 0;
        for (Data d : st.getDefinedData(true)) {
            Object v = null;
            try { v = d.getValue(); } catch (Exception e) { }
            if (v == null) continue;
            String s = v.toString();
            boolean hit = false;
            for (String q : pad) if (s.toLowerCase().contains(q.toLowerCase())) hit = true;
            if (!hit) continue;
            if (++n > 150) break;
            println("STR " + d.getAddress() + " " + s.replace("\n", " ").replace("\r", " "));
            for (Reference r : getReferencesTo(d.getAddress())) {
                Function f = fm.getFunctionContaining(r.getFromAddress());
                println("    xref -> " + (f != null ? f.getName() : "?"));
            }
        }
        println("=== FUNCOES (nome)");
        int m = 0;
        String[] kn = {"Serialize", "Simul", "Conect", "Cable", "Dibujo", "Libreria",
                       "Simbol", "CDib", "CADe_SIMUDoc"};
        for (Function f : fm.getFunctions(true)) {
            String nm = f.getName();
            for (String q : kn) {
                if (nm.toLowerCase().contains(q.toLowerCase())) {
                    println("FUN " + f.getEntryPoint() + " " + nm);
                    if (++m > 100) return;
                    break;
                }
            }
        }
    }
}
