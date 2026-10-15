// draw_dump.java <saida.txt> — extrai, SEM decompilador (leve em memória):
//  1) tabela classe -> thunk -> função de desenho, varrendo FUN_0040d2b0 (despacho do Draw):
//     "CMP dword ptr [reg+reg*4+0x2024],<id>" seguido de "CALL <thunk 0x401000-0x410000>".
//  2) para cada função de desenho, as strings de comando ("LINE,..", "NUME,..", ...) na
//     ordem de endereço (PUSH/MOV de endereço de string) e os rótulos de pino default.
// Saída: linhas "CLASS <id> <thunk> <func>" e "  <addr> <string>".
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class draw_dump extends GhidraScript {
    public void run() throws Exception {
        String outp = getScriptArgs()[0];
        PrintWriter w = new PrintWriter(new FileWriter(outp));
        Address dsp = toAddr(0x40d2b0L);
        Function disp = getFunctionAt(dsp);
        InstructionIterator it = currentProgram.getListing().getInstructions(disp.getBody(), true);
        List<Long> cur = new ArrayList<>();
        // classe -> thunk (primeira ocorrência por classe)
        LinkedHashMap<Long, Set<Long>> cls2t = new LinkedHashMap<>();
        while (it.hasNext()) {
            Instruction ins = it.next();
            String m = ins.getMnemonicString();
            if (m.equals("CMP") && ins.getNumOperands() == 2) {
                String s = ins.toString();
                if (s.contains("+ 0x2024]") || s.contains("+ 0x2024],")) {
                    Object[] o = ins.getOpObjects(1);
                    if (o.length > 0 && o[0] instanceof Scalar) cur.add(((Scalar) o[0]).getSignedValue());
                }
            } else if (m.equals("CALL")) {
                Address[] fl = ins.getFlows();
                if (fl.length > 0) {
                    long t = fl[0].getOffset();
                    if (t >= 0x401000L && t <= 0x410000L) {
                        for (Long c : cur) cls2t.computeIfAbsent(c, k -> new LinkedHashSet<>()).add(t);
                        cur.clear();
                    }
                }
            }
        }
        // resolve thunk -> alvo
        Map<Long, Long> thunk2f = new HashMap<>();
        Set<Long> thunks = new TreeSet<>();
        for (Set<Long> s : cls2t.values()) thunks.addAll(s);
        for (long t : thunks) {
            Instruction i = currentProgram.getListing().getInstructionAt(toAddr(t));
            long target = t;
            if (i != null && i.getMnemonicString().equals("JMP")) {
                Address[] fl = i.getFlows();
                if (fl.length > 0) target = fl[0].getOffset();
            }
            thunk2f.put(t, target);
        }
        for (Map.Entry<Long, Set<Long>> e : cls2t.entrySet())
            for (long t : e.getValue())
                w.println(String.format("CLASS %d %06x %06x", e.getKey(), t, thunk2f.get(t)));
        // strings por função (ordem de endereço)
        Set<Long> funcs = new TreeSet<>(thunk2f.values());
        for (long f : funcs) {
            Function fn = getFunctionAt(toAddr(f));
            w.println("FUNC " + String.format("%06x", f));
            if (fn == null) continue;
            InstructionIterator fi = currentProgram.getListing().getInstructions(fn.getBody(), true);
            while (fi.hasNext()) {
                Instruction ins = fi.next();
                for (int k = 0; k < ins.getNumOperands(); k++) {
                    for (Object ob : ins.getOpObjects(k)) {
                        if (ob instanceof Scalar) {
                            long v = ((Scalar) ob).getUnsignedValue();
                            if (v >= 0xb40000L && v < 0xb90000L) {
                                Data d = currentProgram.getListing().getDataAt(toAddr(v));
                                if (d != null && d.hasStringValue()) {
                                    String s = String.valueOf(d.getValue());
                                    if (s.length() <= 80)
                                        w.println(String.format("  %06x %s", ins.getAddress().getOffset(), s));
                                }
                            }
                        }
                    }
                }
            }
        }
        w.close();
        println("ok " + outp);
    }
}
