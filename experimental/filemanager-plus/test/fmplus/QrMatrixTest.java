package fmplus;
import java.nio.file.*;
import java.security.SecureRandom;
public class QrMatrixTest {
  public static void main(String[] args) throws Exception {
    var token=FeatureCore.newFtpsSession("192.168.10.2",2121,1234567L,new SecureRandom());
    var qr=QrMatrix.encode(token.url);
    if(QrMatrix.SIZE!=37||!qr.get(3,3)||qr.get(7,7))throw new AssertionError("QR finder structure");
    Path output=Path.of(args.length>0?args[0]:"/tmp/fmplus-qr.pgm");
    Files.write(output,qr.toPgm(8));
    try{QrMatrix.encode("a".repeat(107));throw new AssertionError("No size limit");}
    catch(IllegalArgumentException expected) { }
    System.out.println("PASS QR generator checks; file="+output+"; payload="+token.url);
  }
}