package fmplus;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.util.Objects;
import java.util.concurrent.CancellationException;

/** Crash-conscious local file copy. SAF/cloud sources require platform-specific adapters. */
public final class SafeTransfer {
  private SafeTransfer() { }
  public enum Conflict { SKIP, OVERWRITE, KEEP_BOTH }
  public enum Status { COPIED, SKIPPED }
  public interface Stop { boolean requested(); }
  public interface Progress { void onProgress(long done,long total,long bytesPerSecond,long etaSeconds); }
  public static final class Result {
    public final Status status; public final Path target; public final long bytes;
    private Result(Status status,Path target,long bytes){this.status=status;this.target=target;this.bytes=bytes;}
  }
  public static Result copy(Path source,Path destination,Conflict conflict,Stop stop,Progress progress) throws IOException {
    Objects.requireNonNull(source);Objects.requireNonNull(destination);Objects.requireNonNull(conflict);
    if(stop==null) stop=()->false;
    source=source.toAbsolutePath().normalize();destination=destination.toAbsolutePath().normalize();
    if(!Files.isRegularFile(source,LinkOption.NOFOLLOW_LINKS)) throw new IOException("Invalid source file");
    if(Files.exists(destination,LinkOption.NOFOLLOW_LINKS)) {
      if(Files.isSymbolicLink(destination)) throw new IOException("Cannot replace symbolic link");
      if(Files.isSameFile(source,destination)) throw new IOException("Source and target are identical");
      if(conflict==Conflict.SKIP)return new Result(Status.SKIPPED,destination,0);
      if(conflict==Conflict.KEEP_BOTH) destination=uniqueTarget(destination);
    }
    Path parent=destination.getParent();if(parent==null)throw new IOException("Invalid destination");
    if(!Files.isDirectory(parent))throw new IOException("Destination directory missing");
    if(stop.requested())throw new CancellationException("Cancelled");
    long total=Files.size(source),done=0;
    long start=System.nanoTime(),lastNotify=0;
    Path partial=Files.createTempFile(parent,".fmplus-copy-",".part");
    try {
      try(FileChannel input=FileChannel.open(source,StandardOpenOption.READ);
          FileChannel output=FileChannel.open(partial,StandardOpenOption.WRITE,StandardOpenOption.TRUNCATE_EXISTING)) {
        ByteBuffer buffer=ByteBuffer.allocateDirect(128*1024);
        while(true) {
          if(stop.requested())throw new CancellationException("Cancelled");
          buffer.clear();int read=input.read(buffer);if(read<0)break;
          buffer.flip();while(buffer.hasRemaining())output.write(buffer);
          done+=read;
          long now=System.nanoTime();
          if(progress!=null && (now-lastNotify >= 100_000_000L || done==total)) {
            long elapsed=Math.max(1,now-start);
            long speed=(long)(done*1_000_000_000.0/elapsed);
            long eta=speed==0?-1:(total-done+speed-1)/speed;
            progress.onProgress(done,total,speed,eta);lastNotify=now;
          }
        }
        output.force(true);
      }
      if(stop.requested())throw new CancellationException("Cancelled");
      // Reject source modification while copying instead of silently publishing a truncated file.
      if(Files.size(source)!=done)throw new IOException("Source file changed while copying");
      try {
        Files.move(partial,destination,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
      } catch(AtomicMoveNotSupportedException e) {
        Files.move(partial,destination,StandardCopyOption.REPLACE_EXISTING);
      }
      return new Result(Status.COPIED,destination,done);
    } finally {Files.deleteIfExists(partial);}
  }
  private static Path uniqueTarget(Path target) throws IOException {
    String file=target.getFileName().toString();
    int dot=file.lastIndexOf('.');String base=dot<=0?file:file.substring(0,dot), ext=dot<=0?"":file.substring(dot);
    for(int i=1;i<=10000;i++) {
      Path candidate=target.resolveSibling(base+" ("+i+")"+ext);
      if(!Files.exists(candidate,LinkOption.NOFOLLOW_LINKS))return candidate;
    }
    throw new IOException("Too many name conflicts");
  }
}