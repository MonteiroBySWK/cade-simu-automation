// srv.java <dir> — "REPL" headless: fica em loop lendo comandos de <dir>/*.cmd e escrevendo <dir>/*.out.
// Mantém o programa e o decompilador abertos (consulta em ~1s em vez de ~90s por -process).
// Comandos (1 por arquivo, uma linha):
//   dec <addr> [seg]      decompila a função que contém addr (timeout em s, padrão 600)
//   xref <addr>           referências a addr (+ função que contém cada uma)
//   str <substr>          strings definidas contendo substr (+ xrefs)
//   dis <addr> <n>        desassembla n instruções
//   bytes <addr> <n>      hexdump
//   callers <addr>        funções que chamam a função em addr
//   callees <addr>        funções chamadas pela função em addr
//   imm <valor>           funções com instruções que usam o escalar <valor> (decimal ou 0x..)
//   immaddr <valor> [fn] endereços das instruções com o escalar (opcional: só dentro da função)
//   fn <substr>           funções cujo nome contém substr
//   rtti                  lista nomes de classe RTTI achados em strings (.?AV)
//   quit
// Uso (shell): echo "dec 0087aca0" > dir/1.cmd ; esperar dir/1.out
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.data.*;
import ghidra.program.model.mem.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public class srv extends GhidraScript {
    DecompInterface di;
    Address A(String s) { return currentProgram.getAddressFactory().getAddress(s); }
    Function fnAt(Address a) { return currentProgram.getFunctionManager().getFunctionContaining(a); }

    public void run() throws Exception {
        String dir = getScriptArgs()[0];
        di = new DecompInterface();
        di.openProgram(currentProgram);
        println("srv pronto em " + dir);
        new File(dir, "READY").createNewFile();
        while (true) {
            File[] fs = new File(dir).listFiles((d, n) -> n.endsWith(".cmd"));
            if (fs == null || fs.length == 0) { Thread.sleep(200); continue; }
            Arrays.sort(fs);
            for (File f : fs) {
                String line = new String(Files.readAllBytes(f.toPath())).trim();
                f.delete();
                StringBuilder out = new StringBuilder();
                try {
                    if (line.equals("quit")) { Files.write(Paths.get(f.getPath().replace(".cmd", ".out")), "bye".getBytes()); return; }
                    handle(line, out);
                } catch (Throwable t) {
                    out.append("ERRO: ").append(t).append('\n');
                }
                Files.write(Paths.get(f.getPath().replace(".cmd", ".tmp")), out.toString().getBytes("ISO-8859-1"));
                new File(f.getPath().replace(".cmd", ".tmp")).renameTo(new File(f.getPath().replace(".cmd", ".out")));
            }
        }
    }

    void handle(String line, StringBuilder o) throws Exception {
        String[] p = line.split("\\s+", 3);
        String op = p[0];
        if (op.equals("dec")) {
            Function f = fnAt(A(p[1]));
            if (f == null) { o.append("sem função em ").append(p[1]).append('\n'); return; }
            int to = p.length > 2 ? Integer.parseInt(p[2].trim()) : 600;
            DecompileResults r = di.decompileFunction(f, to, monitor);
            if (r != null && r.decompileCompleted()) {
                o.append("#### ").append(f.getName()).append(" @").append(f.getEntryPoint()).append('\n');
                for (String l : r.getDecompiledFunction().getC().split("\n"))
                    if (!l.contains("WARNING: Removing unreachable")) o.append(l).append('\n');
            } else o.append("falha no decompile\n");
        } else if (op.equals("xref")) {
            for (Reference r : getReferencesTo(A(p[1]))) {
                Function f = fnAt(r.getFromAddress());
                o.append(r.getFromAddress()).append(' ').append(r.getReferenceType()).append(' ')
                 .append(f == null ? "-" : f.getName() + "@" + f.getEntryPoint()).append('\n');
            }
        } else if (op.equals("str")) {
            String sub = line.substring(4);
            DataIterator it = currentProgram.getListing().getDefinedData(true);
            while (it.hasNext()) {
                Data d = it.next();
                if (!d.hasStringValue()) continue;
                String v = String.valueOf(d.getValue());
                if (v.contains(sub)) {
                    o.append(d.getAddress()).append(" \"").append(v.replace("\n", "\\n")).append("\"");
                    for (Reference r : getReferencesTo(d.getAddress())) {
                        Function f = fnAt(r.getFromAddress());
                        o.append("\n    <- ").append(r.getFromAddress()).append(" ").append(f == null ? "-" : f.getName());
                    }
                    o.append('\n');
                }
            }
        } else if (op.equals("dis")) {
            Address a = A(p[1]); int n = Integer.parseInt(p[2]);
            Listing l = currentProgram.getListing();
            Instruction ins = l.getInstructionAt(a);
            if (ins == null) ins = l.getInstructionAfter(a);
            for (int i = 0; i < n && ins != null; i++) {
                o.append(ins.getAddress()).append("  ").append(ins).append('\n');
                ins = ins.getNext();
            }
        } else if (op.equals("bytes")) {
            Address a = A(p[1]); int n = Integer.parseInt(p[2]);
            byte[] b = new byte[n];
            currentProgram.getMemory().getBytes(a, b);
            for (int i = 0; i < n; i += 16) {
                o.append(a.add(i)).append(": ");
                for (int j = i; j < Math.min(n, i + 16); j++) o.append(String.format("%02x ", b[j] & 0xff));
                o.append('\n');
            }
        } else if (op.equals("callers")) {
            Function f = fnAt(A(p[1]));
            Set<String> seen = new TreeSet<>();
            for (Reference r : getReferencesTo(f.getEntryPoint())) {
                Function c = fnAt(r.getFromAddress());
                seen.add((c == null ? "-" : c.getName() + "@" + c.getEntryPoint()) + "  (call at " + r.getFromAddress() + ")");
            }
            for (String s : seen) o.append(s).append('\n');
        } else if (op.equals("callees")) {
            Function f = fnAt(A(p[1]));
            Set<String> seen = new TreeSet<>();
            for (Function c : f.getCalledFunctions(monitor)) seen.add(c.getName() + "@" + c.getEntryPoint());
            for (String s : seen) o.append(s).append('\n');
        } else if (op.equals("imm")) {
            long v = p[1].startsWith("0x") ? Long.parseLong(p[1].substring(2), 16) : Long.parseLong(p[1]);
            Map<String, Integer> cnt = new TreeMap<>();
            InstructionIterator it = currentProgram.getListing().getInstructions(true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                for (int k = 0; k < ins.getNumOperands(); k++) {
                    for (Object ob : ins.getOpObjects(k)) {
                        if (ob instanceof Scalar && ((Scalar) ob).getSignedValue() == v) {
                            Function f = fnAt(ins.getAddress());
                            String key = f == null ? "-" : f.getName() + "@" + f.getEntryPoint();
                            cnt.merge(key, 1, Integer::sum);
                        }
                    }
                }
            }
            for (Map.Entry<String, Integer> e : cnt.entrySet()) o.append(e.getKey()).append("  x").append(e.getValue()).append('\n');
        } else if (op.equals("immaddr")) {
            // immaddr <valor> [addr-função]  -> endereços exatos das instruções com o escalar
            long v = p[1].startsWith("0x") ? Long.parseLong(p[1].substring(2), 16) : Long.parseLong(p[1]);
            Function only = p.length > 2 ? fnAt(A(p[2])) : null;
            InstructionIterator it = only != null ? currentProgram.getListing().getInstructions(only.getBody(), true)
                                                  : currentProgram.getListing().getInstructions(true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                for (int k = 0; k < ins.getNumOperands(); k++)
                    for (Object ob : ins.getOpObjects(k))
                        if (ob instanceof Scalar && ((Scalar) ob).getSignedValue() == v)
                            o.append(ins.getAddress()).append("  ").append(ins).append('\n');
            }
        } else if (op.equals("cmpstr")) {
            // cmpstr <addrGlobal> [n]: para cada "CMP [addrGlobal], imm" no programa, a 1a string
            // empurrada (PUSH imm -> string definida) nas n instruções seguintes => classe:string
            Address g = A(p[1]);
            int n = p.length > 2 ? Integer.parseInt(p[2].trim()) : 12;
            Listing l = currentProgram.getListing();
            InstructionIterator it = l.getInstructions(true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                if (!ins.getMnemonicString().equals("CMP")) continue;
                boolean hit = false; Long val = null;
                for (int k = 0; k < ins.getNumOperands(); k++)
                    for (Object ob : ins.getOpObjects(k)) {
                        if (ob instanceof Address && ob.equals(g)) hit = true;
                        if (ob instanceof Scalar && k == 1) val = ((Scalar) ob).getSignedValue();
                    }
                if (!hit || val == null) continue;
                Instruction j = ins.getNext(); String s = null;
                for (int i = 0; i < n && j != null && s == null; i++, j = j.getNext()) {
                    if (!j.getMnemonicString().equals("PUSH")) continue;
                    for (Object ob : j.getOpObjects(0)) if (ob instanceof Scalar) {
                        try {
                            Data d = l.getDataAt(A(Long.toHexString(((Scalar) ob).getUnsignedValue())));
                            if (d != null && d.hasStringValue()) s = String.valueOf(d.getValue());
                            else {
                                Address sa = A(Long.toHexString(((Scalar) ob).getUnsignedValue()));
                                if (currentProgram.getMemory().contains(sa)) {
                                    byte[] b = new byte[80]; int m = currentProgram.getMemory().getBytes(sa, b);
                                    int e = 0; while (e < m && b[e] != 0) e++;
                                    if (e >= 3 && e < 80) { boolean ok = true; for (int q = 0; q < e; q++) if ((b[q] & 0xff) < 0x20) ok = false;
                                        if (ok) s = new String(b, 0, e, "ISO-8859-1"); }
                                }
                            }
                        } catch (Exception ex) {}
                    }
                }
                Function f = fnAt(ins.getAddress());
                o.append(val).append('\t').append(ins.getAddress()).append('\t')
                 .append(f == null ? "-" : f.getEntryPoint().toString()).append('\t').append(s == null ? "" : s.replace("\n", "\\n")).append('\n');
            }
        } else if (op.equals("sem")) {
            // sem <addr>[,<addr>...]: por função, em ordem: strings empurradas (S), comparações de
            // campos de estado (K off imm, p/ offsets 0x78a9c/0x30e24/0x7a9dc/0x2eee4 e classe 0x2024)
            // e Ordinal_812 (L = compara rótulo). Base p/ papel: contato NA (estado==1) / NC (==0).
            Listing l = currentProgram.getListing();
            for (String a : p[1].split(",")) {
                Function f = fnAt(A(a.trim()));
                if (f == null) { o.append("FUNC ").append(a).append(" ?\n"); continue; }
                o.append("FUNC ").append(f.getEntryPoint()).append('\n');
                InstructionIterator it = l.getInstructions(f.getBody(), true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    String mn = ins.getMnemonicString();
                    if (mn.equals("PUSH")) {
                        for (Object ob : ins.getOpObjects(0)) if (ob instanceof Scalar) {
                            long v = ((Scalar) ob).getUnsignedValue();
                            if (v < 0xb46000L || v > 0xbec000L) continue;
                            try {
                                byte[] b = new byte[64]; int m = currentProgram.getMemory().getBytes(A(Long.toHexString(v)), b);
                                int e = 0; while (e < m && b[e] != 0) e++;
                                boolean ok = e < 64; for (int q = 0; q < e && ok; q++) if ((b[q] & 0xff) < 0x20) ok = false;
                                if (ok) o.append("  S ").append(new String(b, 0, e, "ISO-8859-1")).append('\n');
                            } catch (Exception ex) {}
                        }
                    } else if (mn.equals("CMP") || (mn.equals("MOV") && ins.getNumOperands() == 2)) {
                        Object[] o0 = ins.getOpObjects(0);
                        Long off = null, imm = null;
                        for (Object ob : o0) if (ob instanceof Scalar) {
                            long v = ((Scalar) ob).getUnsignedValue();
                            if (v == 0x78a9c || v == 0x30e24 || v == 0x7a9dc || v == 0x2eee4 || v == 0x32d64 || v == 0x34ca4) off = v;
                        }
                        if (off == null && mn.equals("CMP")) {
                            boolean cls = false;
                            for (Object ob : o0) if (ob instanceof Scalar && ((Scalar) ob).getUnsignedValue() == 0x2024) cls = true;
                            if (cls) for (Object ob : ins.getOpObjects(1)) if (ob instanceof Scalar) {
                                long v = ((Scalar) ob).getSignedValue();
                                if (v != 4000 && v != 4009 && v != 4010 && v != 4018 && v != 4019 && v != 1 && v != 0 && v != 0xfa1 && v != 0xfac)
                                    o.append("  C ").append(v).append('\n');
                            }
                            continue;
                        }
                        if (off == null) continue;
                        for (Object ob : ins.getOpObjects(1)) if (ob instanceof Scalar) imm = ((Scalar) ob).getSignedValue();
                        if (imm == null) continue;
                        o.append(mn.equals("CMP") ? "  K 0x" : "  W 0x").append(Long.toHexString(off)).append(' ').append(imm).append('\n');
                    } else if (mn.equals("CALL")) {
                        for (Reference r : ins.getReferencesFrom()) {
                            Symbol s = getSymbolAt(r.getToAddress());
                            Function tf = getFunctionAt(r.getToAddress());
                            String nm = tf != null ? tf.getName() : (s != null ? s.getName() : "");
                            if (tf != null && tf.isThunk() && tf.getThunkedFunction(true) != null) nm = tf.getThunkedFunction(true).getName();
                            if (nm.contains("Ordinal_812") || nm.contains("Ordinal_813")) o.append("  L ").append(nm).append('\n');
                        }
                    }
                }
            }
        } else if (op.equals("fn")) {
            String sub = p[1];
            for (Function f : currentProgram.getFunctionManager().getFunctions(true))
                if (f.getName().contains(sub)) o.append(f.getName()).append('@').append(f.getEntryPoint()).append('\n');
        } else if (op.equals("rtti")) {
            DataIterator it = currentProgram.getListing().getDefinedData(true);
            while (it.hasNext()) {
                Data d = it.next();
                if (!d.hasStringValue()) continue;
                String v = String.valueOf(d.getValue());
                if (v.startsWith(".?AV") || v.startsWith(".?AU")) o.append(d.getAddress()).append(' ').append(v).append('\n');
            }
        } else o.append("comando desconhecido: ").append(line).append('\n');
    }
}
