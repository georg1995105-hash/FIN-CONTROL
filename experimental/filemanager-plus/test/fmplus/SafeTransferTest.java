package fmplus;
import java.nio.file.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.CancellationException;
public class SafeTransferTest {
  private static int checked;
  static void ok(boolean b,String m){if(!b)throw new AssertionError(m);checked++;}
  public static void main(String[] args) throws Exception {
    Path tmp=Files.createTempDirectory("fmplus-transfer-");
    try {
      Path from=tmp.resolve("source.bin"),to=tmp.resolve("target.bin");
      byte[] payload=new byte[500000];new Random(12).nextBytes(payload);Files.write(from,payload);
      List<Long> observed=new ArrayList<>();
      SafeTransfer.Result r=SafeTransfer.copy(from,to,SafeTransfer.Conflict.SKIP,()->false,(done,total,speed,eta)->{observed.add(done);ok(total==payload.length,"Total bytes");});
      ok(r.status==SafeTransfer.Status.COPIED,"Copy succeeded");ok(r.bytes==payload.length,"Copy byte count");
      ok(Arrays.equals(Files.readAllBytes(to),payload),"Content exact");ok(!observed.isEmpty(),"Progress emitted");
      Files.write(from,new byte[]{1,2,3});
      r=SafeTransfer.copy(from,to,SafeTransfer.Conflict.SKIP,()->false,null);
      ok(r.status==SafeTransfer.Status.SKIPPED,"Skip conflict");ok(Files.size(to)==payload.length,"Skip preserves old destination");
      r=SafeTransfer.copy(from,to,SafeTransfer.Conflict.KEEP_BOTH,()->false,null);
      ok(r.target.getFileName().toString().equals("target (1).bin"),"Keep both naming");
      ok(Arrays.equals(Files.readAllBytes(r.target),new byte[]{1,2,3}),"Keep both content");
      try {SafeTransfer.copy(from,from,SafeTransfer.Conflict.OVERWRITE,()->false,null);throw new AssertionError("overwrote source");}
      catch(IOException expected){checked++;}
      try {SafeTransfer.copy(from,to,SafeTransfer.Conflict.OVERWRITE,()->true,null);throw new AssertionError("cancel ignored");}
      catch(CancellationException expected){checked++;}
      ok(Files.size(to)==payload.length,"Cancelled copy preserves target");
      r=SafeTransfer.copy(from,to,SafeTransfer.Conflict.OVERWRITE,()->false,null);
      ok(Files.size(to)==3,"Overwrite committed");
      ok(!Files.list(tmp).anyMatch(p->p.toString().endsWith(".part")),"No partial files");
      System.out.println("PASS "+checked+" checks");
    } finally {
      try(var s=Files.walk(tmp)){s.sorted(Comparator.reverseOrder()).forEach(p->{try{Files.deleteIfExists(p);}catch(IOException ignored){}});}
    }
  }
}