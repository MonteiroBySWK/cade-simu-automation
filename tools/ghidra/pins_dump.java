// pins_dump.java <saida.txt> — extrai, SEM decompilador (leve em memória), o material para
// reconstruir os PINOS de cada classe a partir do binário:
//  1) tabela classe -> thunk -> função de desenho, varrendo o despacho do Draw FUN_0040d2b0:
//     último(s) "CMP ...,<imediato>" antes de um "CALL <thunk 0x401000-0x40ffff>".
//  2) para cada função de desenho e suas chamadas (BFS, profundidade <= 3), a sequência em
//     ordem de endereço de: strings referenciadas (comandos "NUME,..", rótulos default "A1",
//     "13"...) e "CALL <função>" (thunks resolvidos), e comparações com campos do doc
//     (+0x19724 orientação, +0x1b664 variante, +0x2024 id) para ver condicionais.
// Saída: "CLASS <id> <thunk> <func>", depois blocos "FUNC <addr>" com linhas
//        "  <addr> S <string>" / "  <addr> C <func>" / "  <addr> K <campo> <imediato>".
// O ponto-pino é definido SÓ pelo comando NUME (FUN_008462f0 grava 0xbd9660/64); ver
// docs/re-engenharia.md §10 para a fórmula.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class pins_dump extends GhidraScript {
    static final long INTERP = 0x8462f0L;

    long resolve(long t) {
        Instruction i = currentProgram.getListing().getInstructionAt(toAddr(t));
        if (i != null && i.getMnemonicString().equals("JMP")) {
            Address[] fl = i.getFlows();
            if (fl.length > 0) return fl[0].getOffset();
        }
        return t;
    }

    public void run() throws Exception {
        String outp = getScriptArgs()[0];
        PrintWriter w = new PrintWriter(new FileWriter(outp));
        Listing L = currentProgram.getListing();
        Function disp = getFunctionAt(toAddr(0x40d2b0L));
        InstructionIterator it = L.getInstructions(disp.getBody(), true);
        List<Long> cur = new ArrayList<>();
        boolean afterCall = true;
        LinkedHashMap<Long, Set<Long>> cls2f = new LinkedHashMap<>();
        while (it.hasNext()) {
            Instruction ins = it.next();
            String m = ins.getMnemonicString();
            if (m.equals("CMP") && ins.getNumOperands() == 2) {
                Object[] o = ins.getOpObjects(1);
                if (o.length == 1 && o[0] instanceof Scalar) {
                    long v = ((Scalar) o[0]).getSignedValue();
                    if (v >= 1 && v <= 40000 && ins.toString().contains("0x2024")) {
                        if (afterCall) { cur.clear(); afterCall = false; }
                        cur.add(v);
                    }
                }
            } else if (m.equals("CALL")) {
                Address[] fl = ins.getFlows();
                if (fl.length > 0) {
                    long t = fl[0].getOffset();
                    if (t >= 0x401000L && t < 0x410000L) {
                        long f = resolve(t);
                        for (Long c : cur) cls2f.computeIfAbsent(c, k -> new LinkedHashSet<>()).add(f);
                        afterCall = true;
                    }
                }
            }
        }
        Set<Long> roots = new TreeSet<>();
        for (Map.Entry<Long, Set<Long>> e : cls2f.entrySet())
            for (long f : e.getValue()) {
                w.println(String.format("CLASS %d %06x", e.getKey(), f));
                roots.add(f);
            }
        // BFS
        Map<Long, Integer> depth = new HashMap<>();
        Deque<Long> q = new ArrayDeque<>();
        for (long r : roots) { depth.put(r, 0); q.add(r); }
        Set<Long> done = new TreeSet<>();
        Map<Long, List<String>> body = new HashMap<>();
        while (!q.isEmpty()) {
            long f = q.poll();
            if (!done.add(f)) continue;
            Function fn = getFunctionAt(toAddr(f));
            List<String> lines = new ArrayList<>();
            body.put(f, lines);
            if (fn == null) continue;
            InstructionIterator fi = L.getInstructions(fn.getBody(), true);
            while (fi.hasNext()) {
                Instruction ins = fi.next();
                String a = String.format("%06x", ins.getAddress().getOffset());
                String m = ins.getMnemonicString();
                if (m.equals("CALL")) {
                    Address[] fl = ins.getFlows();
                    if (fl.length > 0) {
                        long t = resolve(fl[0].getOffset());
                        if (t >= 0x430000L && t < 0x8c0000L && t != INTERP) {
                            lines.add("  " + a + " C " + String.format("%06x", t));
                            int d = depth.get(f) + 1;
                            if (d <= 3 && !depth.containsKey(t)) { depth.put(t, d); q.add(t); }
                        } else if (t == INTERP) lines.add("  " + a + " I");
                    }
                    continue;
                }
                if (m.equals("CMP") && ins.getNumOperands() == 2) {
                    String s = ins.toString();
                    Object[] o = ins.getOpObjects(1);
                    if (o.length == 1 && o[0] instanceof Scalar) {
                        long v = ((Scalar) o[0]).getSignedValue();
                        for (String fld : new String[]{"0x19724", "0x1b664", "0x2024", "0x63aa4", "0x659e4", "0xa1b60"})
                            if (s.contains(fld + "]")) lines.add("  " + a + " K " + fld + " " + v);
                    }
                }
                for (Reference r : ins.getReferencesFrom()) {
                    Data d = L.getDataAt(r.getToAddress());
                    if (d != null && d.hasStringValue()) {
                        String s = String.valueOf(d.getValue());
                        if (s.length() <= 60) lines.add("  " + a + " S " + s);
                    }
                }
            }
        }
        for (long f : done) {
            w.println("FUNC " + String.format("%06x", f));
            for (String s : body.get(f)) w.println(s);
        }
        w.close();
        println("ok " + outp + " classes=" + cls2f.size() + " funcs=" + done.size());
    }
}
