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
