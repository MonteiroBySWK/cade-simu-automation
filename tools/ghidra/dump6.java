// dump6.java <addr> — decompila a função no endereço dado e joga TODO o C em stdout.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class dump6 extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Address addr = currentProgram.getAddressFactory().getAddress(a[0]);
        Function f = getFunctionAt(addr);
        if (f == null) { println("sem função em " + a[0]); return; }
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        DecompileResults res = di.decompileFunction(f, 120, monitor);
        if (res != null && res.decompileCompleted()) {
            println("#### " + f.getName() + " @" + f.getEntryPoint());
            println(res.getDecompiledFunction().getC());
        } else println("falha no decompile");
    }
}
