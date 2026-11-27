package fmplus;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.*;

/** Platform-neutral feature model. Not wired to the proprietary Android application yet. */
public final class FeatureCore {
  private FeatureCore() { }
  public enum View { LIST, GRID, DETAILED, IMAGES, IMAGE_GRID }
  public enum Sort { NAME, DATE, SIZE, EXTENSION }
  public enum Thumbnails { OFF, ON }

  public static final class FolderView {
    public final View view;
    public final Sort sort;
    public final boolean descending;
    public final Thumbnails thumbnails;
    public final int iconSizeDp;
    public final boolean showIcons;
    /** Compatibility constructor for settings written before schema 2. */
    public FolderView(View view, Sort sort, boolean descending, Thumbnails thumbnails) {
      this(view, sort, descending, thumbnails, 48, true);
    }
    public FolderView(View view, Sort sort, boolean descending, Thumbnails thumbnails,
                      int iconSizeDp, boolean showIcons) {
      this.view = Objects.requireNonNull(view);
      this.sort = Objects.requireNonNull(sort);
      this.descending = descending;
      this.thumbnails = Objects.requireNonNull(thumbnails);
      if (iconSizeDp < 24 || iconSizeDp > 160)
        throw new IllegalArgumentException("Icon size must be 24..160 dp");
      this.iconSizeDp = iconSizeDp;
      this.showIcons = showIcons;
    }
    /** First use: detailed list, before any explicit per-folder choice. */
    public static FolderView initialDefault() {
      return new FolderView(View.DETAILED, Sort.NAME, false, Thumbnails.ON, 48, true);
    }
    public static FolderView downloadsDefault() {
      return new FolderView(View.DETAILED, Sort.DATE, true, Thumbnails.ON, 48, true);
    }
  }

  /** One path, one preference set. Never writes a global view or sorting flag. */
  public static final class FolderSettings {
    private final Map<String, FolderView> values = new HashMap<>();
    public synchronized void put(String path, FolderView value) {
      values.put(normalizePath(path), Objects.requireNonNull(value));
    }
    public synchronized FolderView get(String path, FolderView fallback) {
      return values.getOrDefault(normalizePath(path), fallback);
    }
    public synchronized int size() { return values.size(); }
    public synchronized Map<String, FolderView> snapshot() { return new TreeMap<>(values); }
    public synchronized void restore(Map<String, FolderView> incoming) {
      Map<String, FolderView> validated = new HashMap<>();
      for (Map.Entry<String, FolderView> e : incoming.entrySet())
        validated.put(normalizePath(e.getKey()), Objects.requireNonNull(e.getValue()));
      values.clear(); values.putAll(validated);
    }
  }

  public static String normalizePath(String path) {
    if (path == null || path.trim().isEmpty()) throw new IllegalArgumentException("Empty folder");
    String clean = path.replace('\\', '/').replaceAll("/+", "/");
    while (clean.length() > 1 && clean.endsWith("/")) clean = clean.substring(0, clean.length() - 1);
    // Do not collapse URI scheme (content:// or smb://) or decode encoded path segments.
    if (path.contains("://")) {
      int i = path.indexOf("://");
      String scheme = path.substring(0, i + 3);
      String value = path.substring(i + 3).replaceAll("/+", "/");
      while (value.endsWith("/") && !value.isEmpty()) value = value.substring(0, value.length() - 1);
      return scheme.toLowerCase(Locale.ROOT) + value;
    }
    return clean;
  }

  /** Exact, whitelisted, versioned backup. Does not export credentials or arbitrary app preferences. */
  public static byte[] exportSettings(Map<String, FolderView> folders) throws IOException {
    if (folders.size() > 10000) throw new IllegalArgumentException("Too many folders");
    Properties props = new Properties(); props.setProperty("schema", "2");
    int i=0;
    for (Map.Entry<String, FolderView> e : new TreeMap<>(folders).entrySet()) {
      String path = normalizePath(e.getKey()); FolderView v = e.getValue();
      String prefix = "folder." + i++ + ".";
      props.setProperty(prefix + "path", path);
      props.setProperty(prefix + "view", v.view.name());
      props.setProperty(prefix + "sort", v.sort.name());
      props.setProperty(prefix + "desc", Boolean.toString(v.descending));
      props.setProperty(prefix + "thumbs", v.thumbnails.name());
      props.setProperty(prefix + "iconSizeDp", Integer.toString(v.iconSizeDp));
      props.setProperty(prefix + "showIcons", Boolean.toString(v.showIcons));
    }
    props.setProperty("count", String.valueOf(i));
    ByteArrayOutputStream text = new ByteArrayOutputStream(); props.store(text,"FileManager+ safe folder display backup");
    byte[] payload=text.toByteArray();
    if (payload.length > 1_000_000) throw new IOException("Backup exceeds safe size");
    ByteArrayOutputStream result = new ByteArrayOutputStream();
    try (ZipOutputStream zip = new ZipOutputStream(result)) {
      zip.putNextEntry(new ZipEntry("folder-display.properties")); zip.write(payload); zip.closeEntry();
      zip.putNextEntry(new ZipEntry("sha256.txt")); zip.write(hex(sha256(payload)).getBytes(StandardCharsets.US_ASCII)); zip.closeEntry();
    }
    return result.toByteArray();
  }

  public static Map<String, FolderView> importSettings(byte[] backup) throws IOException {
    if (backup == null || backup.length > 2_000_000) throw new IOException("Invalid backup size");
    byte[] payload=null,checksum=null;
    try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(backup))) {
      ZipEntry entry;
      while ((entry=zip.getNextEntry()) != null) {
        if (entry.isDirectory()) throw new IOException("Unexpected directory");
        if (!entry.getName().equals("folder-display.properties") && !entry.getName().equals("sha256.txt"))
          throw new IOException("Unexpected entry: " + entry.getName());
        ByteArrayOutputStream out=new ByteArrayOutputStream();
        byte[] chunk=new byte[4096];int r;
        while ((r=zip.read(chunk)) != -1) { if (out.size()+r > 1_000_000) throw new IOException("Oversize entry"); out.write(chunk,0,r); }
        if (entry.getName().equals("folder-display.properties")) { if(payload!=null) throw new IOException("Duplicate entry"); payload=out.toByteArray(); }
        else { if (checksum!=null) throw new IOException("Duplicate checksum"); checksum=out.toByteArray(); }
      }
    }
    if (payload==null || checksum==null || !MessageDigest.isEqual(hex(sha256(payload)).getBytes(StandardCharsets.US_ASCII),checksum))
      throw new IOException("Missing or invalid checksum");
    Properties props = new Properties(); props.load(new ByteArrayInputStream(payload));
    String schema = props.getProperty("schema");
    if (!"1".equals(schema) && !"2".equals(schema))
      throw new IOException("Unsupported schema");
    int count;
    try { count=Integer.parseInt(props.getProperty("count", "-1")); }
    catch (NumberFormatException e) { throw new IOException("Bad count",e); }
    if (count < 0 || count > 10000) throw new IOException("Bad count");
    Map<String, FolderView> result=new TreeMap<>();
    try {
      for (int i=0;i<count;i++) {
        String p="folder."+i+"."; String path=normalizePath(props.getProperty(p+"path"));
        boolean descending = parseBooleanStrict(props.getProperty(p+"desc"));
        boolean showIcons = "1".equals(schema) || parseBooleanStrict(props.getProperty(p+"showIcons"));
        int iconSize = "1".equals(schema) ? 48 : Integer.parseInt(props.getProperty(p+"iconSizeDp"));
        FolderView fv = new FolderView(
          View.valueOf(props.getProperty(p+"view")),
          Sort.valueOf(props.getProperty(p+"sort")),
          descending, Thumbnails.valueOf(props.getProperty(p+"thumbs")), iconSize, showIcons);
        if (result.put(path,fv)!=null) throw new IOException("Duplicate path");
      }
    } catch (NullPointerException|IllegalArgumentException e) { throw new IOException("Invalid settings",e); }
    if (props.size() != 2 + count * ("1".equals(schema) ? 5 : 7))
      throw new IOException("Unexpected settings");
    return result;
  }

  private static boolean parseBooleanStrict(String value) {
    if ("true".equals(value)) return true;
    if ("false".equals(value)) return false;
    throw new IllegalArgumentException("Invalid boolean setting");
  }

  private static byte[] sha256(byte[] b) {
    try { return MessageDigest.getInstance("SHA-256").digest(b); }
    catch (java.security.NoSuchAlgorithmException e) { throw new AssertionError(e); }
  }
  private static String hex(byte[] b) {StringBuilder sb=new StringBuilder();for(byte v:b) sb.append(String.format(Locale.ROOT,"%02x",v & 255));return sb.toString();}

  /** D-Pad navigation for grid with focusable cards; -1 means no available target. */
  public static int nextFocus(int current,int columns, boolean[] focusable,int dx,int dy) {
    if(columns<=0||focusable==null||current<0||current>=focusable.length) return -1;
    if((Math.abs(dx)+Math.abs(dy))!=1) throw new IllegalArgumentException("Expected a direction");
    int row=current/columns,col=current%columns;
    while(true) {
      row+=dy; col+=dx;
      if(row<0||col<0||col>=columns||row*columns+col>=focusable.length) return -1;
      int i=row*columns+col;if(focusable[i])return i;
    }
  }
}