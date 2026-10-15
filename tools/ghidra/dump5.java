// dump5.java — caça a biblioteca de símbolos e a rotina de simulação/conexão.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class dump5 extends GhidraScript {
    public void run() throws Exception {
        Program p = currentProgram;
        FunctionManager fm = p.getFunctionManager();
        Listing st = p.getListing();
        String[] alvo = {"Simul", "simul", "Conex", "conex", "Enlaz", "Liga", "Puntos", "puntos",
                         "Contactor", "Rele", "Rel\u00e9", "Motor", "Pulsador", "Lampara", "L\u00e1mpara",
                         "Contacto", "Borna", "Cable", "Setas", "Simb", "Simbol", "Bibliotec"};
        java.util.LinkedHashMap<Function, java.util.LinkedHashSet<String>> fns = new java.util.LinkedHashMap<>();
        for (Data d : st.getDefinedData(true)) {
            Object v = null;
            try { v = d.getValue(); } catch (Exception e) { }
            if (v == null) continue;
            String s = v.toString();
            for (String q : alvo) {
                if (s.contains(q)) {
                    for (Reference r : getReferencesTo(d.getAddress())) {
                        Function f = fm.getFunctionContaining(r.getFromAddress());
                        if (f != null) {
                            fns.computeIfAbsent(f, k -> new java.util.LinkedHashSet<>()).add(s);
                        }
                    }
                    break;
                }
            }
        }
        for (Function f : fns.keySet()) {
            println("FN " + f.getName() + " @" + f.getEntryPoint() + "  <== " + fns.get(f));
        }
    }
}
